interface HierarchySkillLike {
  skill_id: string;
  canonical_name: string;
  hierarchy_level?: number;
  parent_skill_ids?: string[];
}

export interface L1SkillOption {
  skillId: string;
  label: string;
}

export interface L1SkillResolver {
  getL1SkillIds: (skillId: string) => string[];
  getL1SkillLabel: (l1SkillId: string) => string | null;
  getL1SkillOptions: (skillIds?: Iterable<string>) => L1SkillOption[];
}

const KNOWN_L1_LABELS: Record<string, string> = {
  skill_adventure_adventure: "Adventure",
  skill_creative_creativity: "Creativity",
  skill_mental_mental_wellbeing: "Mental Wellbeing",
  skill_physical_physical_health: "Physical Health",
  skill_professional_professional_growth: "Professional Growth",
  skill_social_relationships: "Relationships",
};

const FALLBACK_L1_BY_PREFIX: Record<string, string> = {
  adventure: "skill_adventure_adventure",
  creative: "skill_creative_creativity",
  mental: "skill_mental_mental_wellbeing",
  physical: "skill_physical_physical_health",
  professional: "skill_professional_professional_growth",
  social: "skill_social_relationships",
};

function getSkillPrefix(skillId: string): string {
  return skillId.replace(/^skill_/, "").split("_")[0] ?? "";
}

function isL1Skill(skill: HierarchySkillLike): boolean {
  return skill.hierarchy_level === 1 || (skill.parent_skill_ids?.length ?? 0) === 0;
}

function formatSkillId(skillId: string): string {
  return skillId
    .replace(/^skill_/, "")
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function buildL1SkillResolver(
  skills: readonly HierarchySkillLike[]
): L1SkillResolver {
  const byId = new Map<string, HierarchySkillLike>();
  skills.forEach((skill) => byId.set(skill.skill_id, skill));

  const memo = new Map<string, string[]>();

  const getL1SkillLabel = (l1SkillId: string): string | null => {
    const fromHierarchy = byId.get(l1SkillId)?.canonical_name?.trim();
    if (fromHierarchy) return fromHierarchy;
    if (KNOWN_L1_LABELS[l1SkillId]) return KNOWN_L1_LABELS[l1SkillId];
    return l1SkillId ? formatSkillId(l1SkillId) : null;
  };

  const sortRootIds = (rootIds: Iterable<string>): string[] =>
    Array.from(new Set(rootIds)).sort((a, b) => {
      const labelA = getL1SkillLabel(a) ?? a;
      const labelB = getL1SkillLabel(b) ?? b;
      return labelA.localeCompare(labelB) || a.localeCompare(b);
    });

  const getFallbackRootId = (skillId: string): string | null => {
    const prefix = getSkillPrefix(skillId);
    return FALLBACK_L1_BY_PREFIX[prefix] ?? null;
  };

  const resolveL1SkillIds = (skillId: string, visiting: Set<string>): string[] => {
    const cached = memo.get(skillId);
    if (cached) return cached;
    if (visiting.has(skillId)) return [];

    const skill = byId.get(skillId);
    if (!skill) {
      const fallback = getFallbackRootId(skillId);
      const resolved = fallback ? [fallback] : [];
      memo.set(skillId, resolved);
      return resolved;
    }

    if (isL1Skill(skill)) {
      const resolved = [skill.skill_id];
      memo.set(skillId, resolved);
      return resolved;
    }

    visiting.add(skillId);
    const rootIds = new Set<string>();
    const parentIds = skill.parent_skill_ids ?? [];
    parentIds.forEach((parentId) => {
      resolveL1SkillIds(parentId, visiting).forEach((rootId) => rootIds.add(rootId));
    });
    visiting.delete(skillId);

    if (rootIds.size === 0) {
      const fallback = getFallbackRootId(skillId);
      if (fallback) rootIds.add(fallback);
    }

    const resolved = sortRootIds(rootIds);
    memo.set(skillId, resolved);
    return resolved;
  };

  const getL1SkillIds = (skillId: string): string[] =>
    resolveL1SkillIds(skillId, new Set<string>());

  const getL1SkillOptions = (skillIds?: Iterable<string>): L1SkillOption[] => {
    const rootIds = new Set<string>();

    if (skillIds) {
      for (const skillId of skillIds) {
        getL1SkillIds(skillId).forEach((rootId) => rootIds.add(rootId));
      }
    } else {
      skills.forEach((skill) => {
        if (isL1Skill(skill)) rootIds.add(skill.skill_id);
        getL1SkillIds(skill.skill_id).forEach((rootId) => rootIds.add(rootId));
      });
    }

    return sortRootIds(rootIds).map((skillId) => ({
      skillId,
      label: getL1SkillLabel(skillId) ?? skillId,
    }));
  };

  return {
    getL1SkillIds,
    getL1SkillLabel,
    getL1SkillOptions,
  };
}
