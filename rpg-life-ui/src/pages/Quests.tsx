import { useMemo, useState } from "react";
import { QuestList } from "@/components/quests/QuestList";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, Search } from "lucide-react";
import { Quest, QuestScope, QuestType } from "@/types/quest";
import { useQuests, useCompleteQuest } from "@/hooks/useQuests";
import { useUser } from "@/contexts/UserContext";
import { UserIdSelector } from "@/components/user/UserIdSelector";

type QuestScopeFilter = "all" | QuestScope;
type QuestTypeFilter = "all" | QuestType;
type RelatedSkillFilter = "all" | string;
type RelatedThemeFilter = "all" | string;

function formatSkillLabel(name: string, level?: number | null): string {
  if (typeof level === "number" && Number.isFinite(level) && level > 0) {
    return `L${level} - ${name}`;
  }
  return name;
}

export function Quests() {
  const { user } = useUser();
  const { data: quests = [], isLoading, error } = useQuests(user?.id ?? "");
  const completeQuestMutation = useCompleteQuest();
  const [searchQuery, setSearchQuery] = useState("");
  const [scopeFilter, setScopeFilter] = useState<QuestScopeFilter>("all");
  const [typeFilter, setTypeFilter] = useState<QuestTypeFilter>("all");
  const [skillFilter, setSkillFilter] = useState<RelatedSkillFilter>("all");
  const [themeFilter, setThemeFilter] = useState<RelatedThemeFilter>("all");

  const relatedSkillOptions = useMemo(
    () => {
      const options = new Map<string, { label: string; levelSort: number }>();

      const upsertOption = (
        value: string,
        label: string,
        hierarchyLevel?: number | null
      ) => {
        const levelSort =
          typeof hierarchyLevel === "number" && Number.isFinite(hierarchyLevel)
            ? hierarchyLevel
            : 9_999;
        const existing = options.get(value);
        if (!existing || levelSort < existing.levelSort) {
          options.set(value, { label, levelSort });
        }
      };

      quests.forEach((quest) => {
        const skillName = quest.related_skill_name?.trim();
        const sourceSkillId = quest.related_skill_source_id?.trim();

        if (sourceSkillId) {
          upsertOption(
            sourceSkillId,
            formatSkillLabel(
              skillName || sourceSkillId,
              quest.related_skill_hierarchy_level
            ),
            quest.related_skill_hierarchy_level
          );
        } else if (skillName) {
          // Fallback for skills without global hierarchy mapping.
          upsertOption(`name:${skillName}`, skillName);
        }

        (quest.related_skill_ancestor_skills ?? []).forEach((ancestor) => {
          const ancestorName = ancestor.canonical_name?.trim();
          const ancestorSourceId = ancestor.source_skill_id?.trim();
          if (!ancestorName || !ancestorSourceId) return;
          upsertOption(
            ancestorSourceId,
            formatSkillLabel(ancestorName, ancestor.hierarchy_level),
            ancestor.hierarchy_level
          );
        });
      });

      return Array.from(options.entries())
        .map(([value, meta]) => ({
          value,
          label: meta.label,
          levelSort: meta.levelSort,
        }))
        .sort((a, b) =>
          a.levelSort === b.levelSort
            ? a.label.localeCompare(b.label)
            : a.levelSort - b.levelSort
        );
    },
    [quests]
  );

  const relatedThemeOptions = useMemo(
    () =>
      Array.from(
        new Set(
          quests
            .flatMap((quest) => quest.related_themes ?? [])
            .map((theme) => theme.trim())
            .filter((theme) => theme.length > 0)
        )
      ).sort((a, b) => a.localeCompare(b)),
    [quests]
  );

  const handleQuestComplete = async (quest: Quest) => {
    if (!user) return;
    await completeQuestMutation.mutateAsync({ questId: quest.quest_id, userId: user.id });
  };

  const filteredQuests = useMemo(
    () =>
      quests.filter((quest) => {
        const matchesSearch = quest.quest_name
          .toLowerCase()
          .includes(searchQuery.toLowerCase());
        const matchesScope =
          scopeFilter === "all" || quest.quest_scope === scopeFilter;
        const matchesType =
          typeFilter === "all" || quest.quest_type === typeFilter;
        const matchesSkill =
          skillFilter === "all" ||
          (() => {
            if (skillFilter.startsWith("name:")) {
              return quest.related_skill_name === skillFilter.slice(5);
            }
            if (quest.related_skill_source_id === skillFilter) {
              return true;
            }
            const ancestorIds = (quest.related_skill_ancestor_skills ?? []).map(
              (ancestor) => ancestor.source_skill_id
            );
            return ancestorIds.includes(skillFilter);
          })();
        const matchesTheme =
          themeFilter === "all" || (quest.related_themes ?? []).includes(themeFilter);
        return (
          matchesSearch &&
          matchesScope &&
          matchesType &&
          matchesSkill &&
          matchesTheme
        );
      }),
    [quests, searchQuery, scopeFilter, typeFilter, skillFilter, themeFilter]
  );

  if (!user) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Quests</h1>
        <UserIdSelector />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Quests</h1>
          <p className="text-muted-foreground">Loading your quests...</p>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Quests</h1>
          <p className="text-destructive">Error loading quests: {(error as Error).message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Quests</h1>
          <p className="text-muted-foreground">
            Active challenges and goals
          </p>
        </div>
        <Button>
          <Plus className="w-4 h-4 mr-2" />
          Create Quest
        </Button>
      </div>

      <div className="flex items-center gap-4 flex-wrap">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search quests..."
            className="pl-9"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <Select
          value={scopeFilter}
          onValueChange={(v) => setScopeFilter(v as QuestScopeFilter)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Quest Scope" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Scopes</SelectItem>
            <SelectItem value="instant">Instant</SelectItem>
            <SelectItem value="longterm">Long-term</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={typeFilter}
          onValueChange={(v) => setTypeFilter(v as QuestTypeFilter)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Quest Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="one_time">One-time</SelectItem>
            <SelectItem value="cumulative">Cumulative</SelectItem>
            <SelectItem value="recursive">Recurring</SelectItem>
            <SelectItem value="streak">Streak</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={skillFilter}
          onValueChange={(v) => setSkillFilter(v as RelatedSkillFilter)}
        >
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Related Skill" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All skills</SelectItem>
            {relatedSkillOptions.map((skill) => (
              <SelectItem key={skill.value} value={skill.value}>
                {skill.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={themeFilter}
          onValueChange={(v) => setThemeFilter(v as RelatedThemeFilter)}
        >
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Related Theme" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All themes</SelectItem>
            {relatedThemeOptions.map((theme) => (
              <SelectItem key={theme} value={theme}>
                {theme}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {quests.length > 0 && filteredQuests.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-muted-foreground">No quests match your filters.</p>
        </div>
      ) : (
        <QuestList
          quests={filteredQuests}
          onQuestComplete={handleQuestComplete}
        />
      )}
    </div>
  );
}
