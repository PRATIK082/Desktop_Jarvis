import { useAssistantStore } from "../../stores/assistant";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { Card, CardHeader } from "./Card";

export interface ApprovalCardProps {
  onApproveOnce: () => void;
  onRemember: () => void;
  onDeny: () => void;
  onCancel: () => void;
}

export function ApprovalCardDisplay({
  onApproveOnce,
  onRemember,
  onDeny,
  onCancel,
}: ApprovalCardProps) {
  const { pendingApproval, setPendingApproval } = useAssistantStore();

  if (!pendingApproval) return null;

  const riskBadges: Record<number, string> = {
    0: "no approval needed",
    1: "approval may be remembered",
    2: "preview required",
    3: "denied by default",
  };

  return (
    <Card className="max-w-md border-status-warn/30 bg-surface-graphite/80">
      <CardHeader
        title="Action proposed"
        subtitle="JARVIS wants to perform an action"
      />
      <div className="space-y-3">
        <div>
          <p className="text-sm font-medium text-light">
            {pendingApproval.tool_id}
          </p>
          <p className="text-xs text-surface-panel">{pendingApproval.reason}</p>
        </div>
        <div className="text-xs text-surface-panel">
          <strong>Expected effect:</strong> {pendingApproval.expected_effect}
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="warn">{pendingApproval.risk_level}</Badge>
          <span className="text-xs">
            {riskBadges[pendingApproval.risk_level] ?? ""}
          </span>
        </div>
        <div className="flex gap-2">
          <Button
            variant="primary"
            onClick={() => {
              onApproveOnce();
              setPendingApproval(null);
            }}
          >
            Approve once
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              onRemember();
              setPendingApproval(null);
            }}
          >
            Remember
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              onDeny();
              setPendingApproval(null);
            }}
          >
            Deny
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              onCancel();
              setPendingApproval(null);
            }}
          >
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}
