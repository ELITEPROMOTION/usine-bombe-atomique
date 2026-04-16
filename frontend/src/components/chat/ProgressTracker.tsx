import type { Task } from "@/types/task.types";

const STEPS: Task["status"][] = [
  "pending", "analyzing", "planning", "distributing",
  "executing", "validating", "completed",
];

export function ProgressTracker({ task }: { task: Task | null }) {
  if (!task) return null;
  const currentIdx = STEPS.indexOf(task.status);

  return (
    <div style={{ padding: 12, borderBottom: "1px solid #374151" }}>
      <div style={{ fontSize: 12, marginBottom: 6, color: "#9ca3af" }}>
        Task {task.id.slice(0, 8)} - score {task.validation_score.toFixed(2)} - rework {task.rework_count}/5
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        {STEPS.map((step, i) => (
          <div key={step} style={{
            flex: 1, height: 6, borderRadius: 3,
            background: i <= currentIdx ? "#10b981" : "#374151",
          }} title={step} />
        ))}
      </div>
    </div>
  );
}
