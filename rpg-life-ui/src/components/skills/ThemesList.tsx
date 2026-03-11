import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useRealmPreferences } from "@/hooks/useRealmPreferences";
import { Theme } from "@/types/theme";

interface ThemesListProps {
  themes: Theme[];
}

function getRankFromLevel(level: number): string | null {
  if (level <= 0) return null;
  if (level < 10) return "F";
  if (level < 20) return "E";
  if (level < 30) return "D";
  if (level < 40) return "C";
  if (level < 50) return "B";
  if (level < 60) return "A";
  if (level < 75) return "S";
  if (level < 100) return "SS";
  return "SSS";
}

export function ThemesList({ themes }: ThemesListProps) {
  const [hoveredThemeId, setHoveredThemeId] = useState<string | null>(null);
  const { getRankLabel } = useRealmPreferences();

  if (themes.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>No themes available yet.</p>
        <p className="text-sm mt-2">
          Themes are seeded automatically for each user. Try refreshing the page.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {themes.map((theme) => {
        const relatedSkillNames = Array.isArray(theme.related_skill_names)
          ? theme.related_skill_names
          : [];
        const hasLevelProgress = theme.current_level > 0 && theme.next_level_xp > 0;
        const levelProgressPercent =
          hasLevelProgress
            ? Math.min((theme.current_level_xp / theme.next_level_xp) * 100, 100)
            : 0;
        const resolvedRank = theme.rank ?? getRankFromLevel(theme.current_level);
        const realmRankLabel = getRankLabel(resolvedRank);
        const rankLine =
          resolvedRank && realmRankLabel ? `${resolvedRank} - ${realmRankLabel}` : null;
        const isHovered = hoveredThemeId === theme.theme_id;
        const skillLabel =
          theme.related_skills_count === 1 ? "related skill" : "related skills";
        const relatedSkillsCountLine = `${theme.related_skills_count} ${skillLabel}`;
        const relatedSkillsLine =
          relatedSkillNames.length > 0
            ? relatedSkillNames.join(", ")
            : theme.related_skills_count > 0
              ? relatedSkillsCountLine
              : "No related skills yet.";

        return (
          <Card
            key={theme.theme_id}
            onMouseEnter={() => setHoveredThemeId(theme.theme_id)}
            onMouseLeave={() =>
              setHoveredThemeId((current) =>
                current === theme.theme_id ? null : current
              )
            }
          >
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <CardTitle className="text-2xl">{theme.name}</CardTitle>
                <div className="flex items-center gap-1 shrink-0 text-primary">
                  <TooltipProvider delayDuration={0}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="text-sm font-semibold cursor-help">Lv</span>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Level</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                  <span className="text-2xl font-bold">{theme.current_level}</span>
                </div>
              </div>
              {isHovered && rankLine && (
                <CardDescription>{rankLine}</CardDescription>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {theme.description ?? "No description available."}
              </p>
              <div className="flex items-center justify-between text-sm">
                <span>Total XP</span>
                <span className="font-medium">{theme.total_xp.toLocaleString()}</span>
              </div>
              {hasLevelProgress && (
                <div className="space-y-1">
                  <Progress value={levelProgressPercent} className="h-2" />
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {theme.current_level_xp.toLocaleString()} /{" "}
                      {theme.next_level_xp.toLocaleString()} XP
                    </span>
                    <span>{levelProgressPercent.toFixed(1)}%</span>
                  </div>
                </div>
              )}
              <div className="text-sm text-muted-foreground">
                {isHovered ? relatedSkillsLine : relatedSkillsCountLine}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
