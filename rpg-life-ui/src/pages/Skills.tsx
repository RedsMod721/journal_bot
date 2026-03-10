import {
  useState,
  lazy,
  Suspense,
  Component,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { SkillList } from "@/components/skills/SkillList";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Search, Grid3x3, List, GitBranch, Loader2, AlertTriangle, RefreshCw } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skill } from "@/types/skill";
import type { SkillHierarchyNode } from "@/types/skillHierarchy";
import { Skeleton } from "@/components/ui/skeleton";
import { useSkills } from "@/hooks/useSkills";
import { useUser } from "@/contexts/UserContext";
import { UserIdSelector } from "@/components/user/UserIdSelector";

// Lazy-load the tree (dagre layout is heavy; only pay the cost on first open)
const SkillTree = lazy(() =>
  import("@/components/skills/SkillTree").then((m) => ({ default: m.SkillTree }))
);

// Static hierarchy data — imported at build time (607 skills)
import hierarchyRaw from "@/data/skill_hierarchy.json";
const HIERARCHY_SKILLS = hierarchyRaw as SkillHierarchyNode[];

interface SkillTreeErrorBoundaryProps {
  children: ReactNode;
}

interface SkillTreeErrorBoundaryState {
  hasError: boolean;
}

class SkillTreeErrorBoundary extends Component<
  SkillTreeErrorBoundaryProps,
  SkillTreeErrorBoundaryState
> {
  state: SkillTreeErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): SkillTreeErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Skill tree render error:", error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Skill tree failed to load
            </CardTitle>
            <CardDescription>
              The rest of your Skills page is still available. Try reloading the tree.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={this.handleRetry} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Retry
            </Button>
          </CardContent>
        </Card>
      );
    }

    return this.props.children;
  }
}

type SortKey = "level" | "xp" | "recent" | "name";
type CategoryFilter =
  | "all"
  | "Physical"
  | "Mental"
  | "Professional"
  | "Creative"
  | "Social";

function sortSkills(skills: Skill[], key: SortKey): Skill[] {
  return [...skills].sort((a, b) => {
    switch (key) {
      case "level":
        return b.current_level - a.current_level;
      case "xp":
        return b.total_xp - a.total_xp;
      case "recent":
        return (
          new Date(b.last_practiced_at).getTime() -
          new Date(a.last_practiced_at).getTime()
        );
      case "name":
        return a.canonical_name.localeCompare(b.canonical_name);
    }
  });
}

export function Skills() {
  const { user } = useUser();
  const { data: skills = [], isLoading, error } = useSkills(user?.id ?? "");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [searchQuery, setSearchQuery] = useState("");
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("level");

  const filteredSkills = sortSkills(
    skills.filter((skill) => {
      const matchesSearch = skill.canonical_name
        .toLowerCase()
        .includes(searchQuery.toLowerCase());
      const matchesCategory =
        category === "all" || skill.category === category;
      return matchesSearch && matchesCategory;
    }),
    sortKey
  );

  if (!user) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Skills</h1>
        <UserIdSelector />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Skills</h1>
          <p className="text-muted-foreground">Loading your skills...</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Skills</h1>
          <p className="text-destructive">Error loading skills: {(error as Error).message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Skills</h1>
          <p className="text-muted-foreground">
            Track your progress across all skills
          </p>
        </div>
      </div>

      <Tabs defaultValue="list">
        <TabsList className="w-fit">
          <TabsTrigger value="list" className="gap-2">
            <Grid3x3 className="w-4 h-4" />
            My Skills
          </TabsTrigger>
          <TabsTrigger value="tree" className="gap-2">
            <GitBranch className="w-4 h-4" />
            Skill Tree
          </TabsTrigger>
        </TabsList>

        {/* ── List tab ── */}
        <TabsContent value="list" className="space-y-6 mt-4">
          {/* Search and Filters */}
          <div className="flex items-center gap-4 flex-wrap">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search skills..."
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <Select
              value={category}
              onValueChange={(v) => setCategory(v as CategoryFilter)}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                <SelectItem value="Physical">Physical</SelectItem>
                <SelectItem value="Mental">Mental</SelectItem>
                <SelectItem value="Professional">Professional</SelectItem>
                <SelectItem value="Creative">Creative</SelectItem>
                <SelectItem value="Social">Social</SelectItem>
              </SelectContent>
            </Select>

            <Select
              value={sortKey}
              onValueChange={(v) => setSortKey(v as SortKey)}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="level">Level (High to Low)</SelectItem>
                <SelectItem value="xp">Total XP</SelectItem>
                <SelectItem value="recent">Recently Practiced</SelectItem>
                <SelectItem value="name">Name (A-Z)</SelectItem>
              </SelectContent>
            </Select>

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

          <SkillList
            skills={filteredSkills}
            variant={viewMode === "list" ? "compact" : "default"}
            onSkillClick={(skill) => console.log("Clicked skill:", skill)}
          />
        </TabsContent>

        {/* ── Skill Tree tab ── */}
        <TabsContent value="tree" className="mt-4">
          <SkillTreeErrorBoundary>
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-64 gap-3 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Building skill tree…
                </div>
              }
            >
              <SkillTree skills={HIERARCHY_SKILLS} />
            </Suspense>
          </SkillTreeErrorBoundary>
        </TabsContent>
      </Tabs>
    </div>
  );
}
