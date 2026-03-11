import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { SkillTree } from "@/components/skills/SkillTree";
import type { SkillHierarchyNode } from "@/types/skillHierarchy";

vi.mock("@xyflow/react", async () => {
  const actual = await vi.importActual<typeof import("@xyflow/react")>(
    "@xyflow/react"
  );

  const passthrough = ({ children }: { children?: ReactNode }) => (
    <div>{children}</div>
  );

  return {
    ...actual,
    ReactFlow: passthrough,
    ReactFlowProvider: passthrough,
    Background: () => <div />,
    Controls: () => <div />,
    MiniMap: () => <div />,
  };
});

describe("SkillTree", () => {
  it("shows discovered/activated legend semantics", () => {
    const skills: SkillHierarchyNode[] = [
      {
        skill_id: "skill_professional_root",
        canonical_name: "Root",
        hierarchy_level: 1,
        parent_skill_ids: [],
        state: "activated",
      },
    ];

    render(<SkillTree skills={skills} />);

    expect(screen.getByText("Full color = activated")).toBeInTheDocument();
    expect(screen.getByText("Dimmed = discovered")).toBeInTheDocument();
  });
});
