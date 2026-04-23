"""Upgrade 4 - Browser Ops Agent (Playwright + human-in-loop).

Ce module automatise la partie non-sensible de l'enregistrement d'un
outil SaaS. Des qu'une etape SENSIBLE est atteinte (OTP, CAPTCHA, paiement,
mot de passe), il cree une FieldRequest et s'arrete jusqu'a reception de
la reponse utilisateur.

Le module est utilisable en mode :
- `dry_run` : genere uniquement les FieldRequest sans lancer Playwright
- `live`    : lance une instance Chromium headless (requiert
              `playwright install chromium` dans le container)

**Securite** : ne jamais persister les mots de passe utilisateur ; ils
transitent uniquement via pending_user_inputs.submission_payload (chiffre
par Postgres + RLS + retention 1h).
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any

from app.intake import field_collector
from app.intake.field_collector import FieldRequest

logger = logging.getLogger(__name__)


@dataclass
class BrowserStep:
    action: str           # goto | fill | click | wait_for | screenshot | expect_text
    target: str = ""      # selector or URL
    value: str = ""       # valeur si fill ; texte attendu si expect_text
    description: str = ""


@dataclass
class ProvisionFlow:
    tool_name: str
    signup_url: str
    steps: list[BrowserStep] = field(default_factory=list)
    required_user_inputs: list[str] = field(default_factory=list)
    # exemples : ["email", "password", "otp", "payment", "captcha"]


@dataclass
class FlowOutcome:
    success: bool
    next_request: FieldRequest | None = None
    captured: dict[str, str] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "captured_keys": list(self.captured.keys()),
            "next_request": self.next_request.to_dict() if self.next_request else None,
        }


class BrowserOpsAgent:
    """Agent de provisioning. dry_run par defaut = securise pour tests."""

    def __init__(self, dry_run: bool = True, headless: bool = True) -> None:
        self.dry_run = dry_run
        self.headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def start(self) -> bool:
        if self.dry_run:
            return True
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except ImportError as exc:
            logger.warning("playwright indisponible : %s", exc)
            return False
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
        except Exception as exc:
            logger.warning("chromium indisponible (playwright install?) : %s", exc)
            await self._playwright.stop()
            self._playwright = None
            return False
        self._page = await self._browser.new_page()
        return True

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._page = None
        self._browser = None
        self._playwright = None

    async def run_step(self, step: BrowserStep) -> bool:
        if self.dry_run or self._page is None:
            logger.info("[dry_run] %s %s %s", step.action, step.target, step.value[:40])
            return True
        page = self._page
        try:
            if step.action == "goto":
                await page.goto(step.target, wait_until="domcontentloaded")
            elif step.action == "fill":
                await page.fill(step.target, step.value)
            elif step.action == "click":
                await page.click(step.target)
            elif step.action == "wait_for":
                await page.wait_for_selector(step.target, timeout=15_000)
            elif step.action == "expect_text":
                content = await page.content()
                return step.value in content
            return True
        except Exception as exc:
            logger.warning("browser step failed: %s - %s", step.action, exc)
            return False

    async def screenshot_b64(self) -> str | None:
        if self.dry_run or self._page is None:
            return None
        try:
            png = await self._page.screenshot(full_page=False)
            return base64.b64encode(png).decode("ascii")
        except Exception:
            return None

    async def execute(
        self, flow: ProvisionFlow, provided_values: dict[str, str] | None = None,
    ) -> FlowOutcome:
        """Execute les steps du flow jusqu'a rencontrer un input sensible manquant.

        Si `provided_values` contient les valeurs deja soumises par l'utilisateur,
        elles sont utilisees pour remplir les champs automatiquement. Sinon,
        retourne un FlowOutcome avec `next_request` a remplir.
        """
        provided_values = provided_values or {}
        await self.start()
        try:
            for step in flow.steps:
                # Substitution template {{email}} par provided_values["email"]
                if step.action == "fill" and step.value.startswith("{{"):
                    key = step.value.strip("{}")
                    if key not in provided_values:
                        req = _field_request_for(key, flow)
                        return FlowOutcome(
                            success=False, next_request=req,
                            message=f"En attente du champ '{key}'",
                        )
                    step.value = provided_values[key]
                ok = await self.run_step(step)
                if not ok:
                    return FlowOutcome(
                        success=False,
                        message=f"Step {step.action} ({step.target}) a echoue",
                    )
                if step.action == "expect_text" and not await self._expect_text(step):
                    # Probablement un CAPTCHA ou une page intermediaire
                    shot = await self.screenshot_b64()
                    if shot:
                        return FlowOutcome(
                            success=False,
                            next_request=field_collector.ask_captcha(shot),
                            message="CAPTCHA / verification intermediaire",
                        )
            return FlowOutcome(success=True, message="Flow termine")
        finally:
            await self.stop()

    async def _expect_text(self, step: BrowserStep) -> bool:
        if self.dry_run or self._page is None:
            return True
        content = await self._page.content()
        return step.value in content


def _field_request_for(key: str, flow: ProvisionFlow) -> FieldRequest:
    if key == "email":
        return field_collector.ask_email()
    if key == "password":
        return field_collector.ask_password()
    if key == "otp":
        return field_collector.ask_otp()
    if key == "captcha":
        return field_collector.ask_captcha(image_b64="", action_url=flow.signup_url)
    if key == "payment":
        return field_collector.ask_payment(amount="?", action_url=flow.signup_url)
    if key == "api_key":
        return field_collector.ask_api_key(flow.tool_name)
    return field_collector.ask_custom(f"Valeur pour {key}", field_id=key)


# Catalogue : definitions de flows pre-enregistres
PREDEFINED_FLOWS: dict[str, ProvisionFlow] = {
    "sonarcloud": ProvisionFlow(
        tool_name="SonarCloud", signup_url="https://sonarcloud.io/sessions/new",
        steps=[
            BrowserStep("goto", "https://sonarcloud.io/sessions/new",
                         description="Page d'accueil"),
            BrowserStep("click", "text=Log in with Email",
                         description="Connexion email"),
            BrowserStep("fill", "input[type=email]", "{{email}}"),
            BrowserStep("fill", "input[type=password]", "{{password}}"),
            BrowserStep("click", "button[type=submit]"),
            BrowserStep("wait_for", "[data-test=org-dashboard]"),
        ],
        required_user_inputs=["email", "password"],
    ),
    "datadog": ProvisionFlow(
        tool_name="Datadog", signup_url="https://www.datadoghq.com/free-datadog-trial/",
        steps=[
            BrowserStep("goto", "https://www.datadoghq.com/free-datadog-trial/"),
            BrowserStep("fill", "input[name=email]", "{{email}}"),
            BrowserStep("fill", "input[name=password]", "{{password}}"),
            BrowserStep("click", "button[type=submit]"),
        ],
        required_user_inputs=["email", "password", "otp"],
    ),
    "supabase": ProvisionFlow(
        tool_name="Supabase", signup_url="https://supabase.com/dashboard/sign-up",
        steps=[
            BrowserStep("goto", "https://supabase.com/dashboard/sign-up"),
            BrowserStep("fill", "input[name=email]", "{{email}}"),
            BrowserStep("fill", "input[name=password]", "{{password}}"),
            BrowserStep("click", "button[type=submit]"),
            BrowserStep("wait_for", "text=Confirm your email"),
        ],
        required_user_inputs=["email", "password"],
    ),
}


def list_flows() -> list[str]:
    return sorted(PREDEFINED_FLOWS.keys())


def get_flow(tool_id: str) -> ProvisionFlow | None:
    return PREDEFINED_FLOWS.get(tool_id)
