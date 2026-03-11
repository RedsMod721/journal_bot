import { useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Grid3x3, List } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { SkillList } from "@/components/skills/SkillList";
import { SkillTreeView } from "@/components/skills/SkillTreeView";
import { ThemesList } from "@/components/skills/ThemesList";
import { useSkillHierarchy } from "@/hooks/useSkillHierarchy";
import { useThemes } from "@/hooks/useThemes";
import { useUser } from "@/contexts/UserContext";
import { buildL1SkillResolver } from "@/lib/skillHierarchyRoots";
import { UserIdSelector } from "@/components/user/UserIdSelector";

type L1SkillFilter = "all" | string;

export function ThemesSkills() {
  const { user, isLoading: userLoading } = useUser();
  const {
    data: hierarchy,
    isLoading: hierarchyLoading,
    error: hierarchyError,
  } = useSkillHierarchy(user?.id ?? "");
  const {
    data: themes,
    isLoading: themesLoading,
    error: themesError,
  } = useThemes(user?.id ?? "");

  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [searchQuery, setSearchQuery] = useState("");
  const [l1SkillFilter, setL1SkillFilter] = useState<L1SkillFilter>("all");
  const [themeFilter, setThemeFilter] = useState("all");
  const [showDiscovered, setShowDiscovered] = useState(true);
  const [showBlocked, setShowBlocked] = useState(false);

  const l1SkillResolver = useMemo(
    () => buildL1SkillResolver(hierarchy ?? []),
    [hierarchy]
  );
  const l1SkillOptions = useMemo(
    () => l1SkillResolver.getL1SkillOptions(),
    [l1SkillResolver]
  );
  const skillNamesByTheme = useMemo(
    () =>
      new Map(
        (themes ?? []).map((theme) => [
          theme.name,
          new Set(
            (theme.related_skill_names ?? []).map((name) => name.toLowerCase())
          ),
        ])
      ),
    [themes]
  );
  const themeOptions = useMemo(
    () =>
      (themes ?? [])
        .filter((theme) => (theme.related_skill_names ?? []).length > 0)
        .map((theme) => theme.name),
    [themes]
  );

  // Skills shown in "My Skills" tab — activated + optionally discovered
  const mySkills = (hierarchy ?? []).filter((skill) => {
    if (skill.state !== "activated" && skill.state !== "discovered") return false;
    if (skill.state === "discovered" && !showDiscovered) return false;
    if (skill.user_blocked && !showBlocked) return false;

    if (
      searchQuery &&
      !(skill.canonical_name ?? "")
        .toLowerCase()
        .includes(searchQuery.toLowerCase())
    ) {
      return false;
    }

    if (
      l1SkillFilter !== "all" &&
      !l1SkillResolver.getL1SkillIds(skill.skill_id).includes(l1SkillFilter)
    ) {
      return false;
    }

    if (themeFilter !== "all") {
      const themeSkillNames = skillNamesByTheme.get(themeFilter);
      if (!themeSkillNames?.has((skill.canonical_name ?? "").toLowerCase())) {
        return false;
      }
    }

    return true;
  });

  if (userLoading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Themes & Skills</h1>
          <p className="text-muted-foreground">Loading active user...</p>
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Themes & Skills</h1>
          <p className="text-muted-foreground">
            Select an active user before viewing themes and skills.
          </p>
        </div>
        <UserIdSelector />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Themes & Skills</h1>
          <p className="text-muted-foreground">
            Explore skill themes, track your progress, and unlock new abilities
          </p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="my-skills" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="themes">Themes</TabsTrigger>
          <TabsTrigger value="my-skills">My Skills</TabsTrigger>
          <TabsTrigger value="skill-tree">Skill Tree</TabsTrigger>
        </TabsList>

        {/* ── Themes tab ─────────────────────────────────────────────── */}
        <TabsContent value="themes" className="mt-6">
          {themesLoading ? (
            <Skeleton className="h-96 w-full" />
          ) : themesError ? (
            <p className="text-destructive">
              Error loading themes:{" "}
              {themesError instanceof Error ? themesError.message : "Unknown error"}
            </p>
          ) : (
            <ThemesList themes={themes ?? []} />
          )}
        </TabsContent>

        {/* ── My Skills tab ──────────────────────────────────────────── */}
        <TabsContent value="my-skills" className="mt-6 space-y-6">
          {hierarchyLoading ? (
            <Skeleton className="h-96 w-full" />
          ) : hierarchyError ? (
            <p className="text-destructive">
              Error loading skills:{" "}
              {hierarchyError instanceof Error
                ? hierarchyError.message
                : "Unknown error"}
            </p>
          ) : (
            <>
              {/* Filters */}
              <div className="flex flex-wrap items-center gap-4">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search skills…"
                    className="pl-9"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>

                <Select
                  value={l1SkillFilter}
                  onValueChange={(value) => setL1SkillFilter(value as L1SkillFilter)}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="L1 Skill" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All L1 Skills</SelectItem>
                    {l1SkillOptions.map((l1Skill) => (
                      <SelectItem key={l1Skill.skillId} value={l1Skill.skillId}>
                        {l1Skill.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select value={themeFilter} onValueChange={setThemeFilter}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Theme" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All themes</SelectItem>
                    {themeOptions.map((themeName) => (
                      <SelectItem key={themeName} value={themeName}>
                        {themeName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="flex items-center gap-2">
                  <Switch
                    id="show-discovered"
                    checked={showDiscovered}
                    onCheckedChange={setShowDiscovered}
                  />
                  <Label htmlFor="show-discovered">Show Discovered</Label>
                </div>

                <div className="flex items-center gap-2">
                  <Switch
                    id="show-blocked"
                    checked={showBlocked}
                    onCheckedChange={setShowBlocked}
                  />
                  <Label htmlFor="show-blocked">Show Blocked</Label>
                </div>

                <div className="flex gap-1 border border-border rounded-lg p-1">
                  <Button
                    variant={viewMode === "grid" ? "default" : "ghost"}
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setViewMode("grid")}
                  >
                    <Grid3x3 className="h-4 w-4" />
                  </Button>
                  <Button
                    variant={viewMode === "list" ? "default" : "ghost"}
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setViewMode("list")}
                  >
                    <List className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              {/* Skills list / grid */}
              {mySkills.length > 0 ? (
                <SkillList
                  skills={mySkills}
                  variant={viewMode === "list" ? "compact" : "default"}
                  showParents
                />
              ) : (
                <div className="text-center py-12 text-muted-foreground">
                  <p>No skills match your filters.</p>
                  <p className="text-sm mt-2">
                    Try adjusting your search or toggling the filters above.
                  </p>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ── Skill Tree tab ─────────────────────────────────────────── */}
        <TabsContent value="skill-tree" className="mt-6">
          {hierarchyLoading ? (
            <Skeleton className="h-96 w-full" />
          ) : hierarchyError ? (
            <p className="text-destructive">
              Error loading skill tree:{" "}
              {hierarchyError instanceof Error
                ? hierarchyError.message
                : "Unknown error"}
            </p>
          ) : (
            <SkillTreeView skills={hierarchy ?? []} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
