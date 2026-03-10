import { SkillCard } from "./SkillCard";
import { Skill } from "@/types/skill";

interface SkillListProps {
  skills: Skill[];
  variant?: "default" | "compact";
  onSkillClick?: (skill: Skill) => void;
  className?: string;
}

export function SkillList({
  skills,
  variant = "default",
  onSkillClick,
  className,
}: SkillListProps) {
  if (skills.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">No skills practiced yet.</p>
        <p className="text-sm text-muted-foreground mt-2">
          Submit a journal entry to start tracking skills!
        </p>
      </div>
    );
  }

  if (variant === "compact") {
    return (
      <div className={className}>
        <div className="space-y-2">
          {skills.map((skill) => (
            <SkillCard
              key={skill.skill_id}
              skill={skill}
              variant="compact"
              onClick={() => onSkillClick?.(skill)}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {skills.map((skill) => (
          <SkillCard
            key={skill.skill_id}
            skill={skill}
            onClick={() => onSkillClick?.(skill)}
          />
        ))}
      </div>
    </div>
  );
}
