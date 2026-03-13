import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import apiClient, { apiPath } from "@/lib/api";
import { useUser } from "@/contexts/UserContext";

interface DimensionScores {
  physical: number;
  mental: number;
  social: number;
  productivity: number;
  rest: number;
  growth: number;
  creative: number;
}

interface HarmonyResponse {
  user_id: string;
  dimensions: DimensionScores;
  overall_balance: number;
  overwork_stage: number;
  overwork_consecutive_days: number;
  updated_at: string;
}

const DIMENSIONS: { key: keyof DimensionScores; label: string }[] = [
  { key: "physical", label: "Physical" },
  { key: "mental", label: "Mental" },
  { key: "social", label: "Social" },
  { key: "productivity", label: "Productivity" },
  { key: "rest", label: "Rest" },
  { key: "growth", label: "Growth" },
  { key: "creative", label: "Creative" },
];

const CX = 150;
const CY = 150;
const R = 100;
const N = DIMENSIONS.length;
const LABEL_R = 128;

function polarPoint(value: number, index: number, radius: number) {
  const angle = (Math.PI * 2 * index) / N - Math.PI / 2;
  return {
    x: CX + radius * value * Math.cos(angle),
    y: CY + radius * value * Math.sin(angle),
  };
}

function gridPoint(index: number, frac: number) {
  const angle = (Math.PI * 2 * index) / N - Math.PI / 2;
  return {
    x: CX + R * frac * Math.cos(angle),
    y: CY + R * frac * Math.sin(angle),
  };
}

function buildPolygon(points: { x: number; y: number }[]) {
  return points.map((p) => `${p.x},${p.y}`).join(" ");
}

type BadgeVariant = "default" | "secondary" | "warning" | "destructive" | "outline";

const OVERWORK_CONFIG: Record<
  number,
  { label: string; variant: BadgeVariant; className?: string }
> = {
  0: { label: "Balanced", variant: "default" },
  1: { label: "Watch", variant: "outline", className: "text-amber-500 border-amber-500" },
  2: { label: "Warning", variant: "warning" },
  3: { label: "Crisis", variant: "destructive" },
};

export function HarmonyRadarChart() {
  const { user } = useUser();

  const { data: harmony, isLoading } = useQuery({
    queryKey: ["harmonyDimensions", user?.id],
    queryFn: async () => {
      const { data } = await apiClient.get<HarmonyResponse>(
        apiPath("/harmony/dimensions"),
        { params: { user_id: user?.id } }
      );
      return data;
    },
    enabled: !!user?.id,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Life Balance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="w-48 h-48 rounded-full mx-auto" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!harmony) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Life Balance</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-8">
            No harmony data yet — start journaling to see your balance!
          </p>
        </CardContent>
      </Card>
    );
  }

  // Build data polygon points
  const dataPoints = DIMENSIONS.map((d, i) =>
    polarPoint(harmony.dimensions[d.key], i, R)
  );

  // Build grid rings at 33%, 66%, 100%
  const gridRings = [0.33, 0.66, 1.0].map((frac) =>
    buildPolygon(DIMENSIONS.map((_, i) => gridPoint(i, frac)))
  );

  // Axis lines from center to perimeter
  const axisLines = DIMENSIONS.map((_, i) => gridPoint(i, 1));

  // Label positions
  const labelPoints = DIMENSIONS.map((d, i) => {
    const angle = (Math.PI * 2 * i) / N - Math.PI / 2;
    return {
      label: d.label,
      x: CX + LABEL_R * Math.cos(angle),
      y: CY + LABEL_R * Math.sin(angle),
    };
  });

  const stage = harmony.overwork_stage ?? 0;
  const overworkCfg = OVERWORK_CONFIG[stage] ?? OVERWORK_CONFIG[0];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Life Balance</CardTitle>
          <Badge variant={overworkCfg.variant} className={overworkCfg.className}>
            {overworkCfg.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <svg
          viewBox="0 0 300 300"
          className="w-full max-w-xs mx-auto"
          role="img"
          aria-label={`Life balance radar chart. Overall balance: ${(harmony.overall_balance * 100).toFixed(0)}%`}
        >
          {/* Grid rings */}
          {gridRings.map((points, i) => (
            <polygon
              key={i}
              points={points}
              fill="none"
              stroke="currentColor"
              strokeOpacity={0.15}
              strokeWidth={1}
            />
          ))}

          {/* Axis lines */}
          {axisLines.map((pt, i) => (
            <line
              key={i}
              x1={CX}
              y1={CY}
              x2={pt.x}
              y2={pt.y}
              stroke="currentColor"
              strokeOpacity={0.15}
              strokeWidth={1}
            />
          ))}

          {/* Data polygon */}
          <polygon
            points={buildPolygon(dataPoints)}
            fill="#8b5cf6"
            fillOpacity={0.25}
            stroke="#8b5cf6"
            strokeWidth={2}
            strokeOpacity={0.8}
          />

          {/* Data points */}
          {dataPoints.map((pt, i) => (
            <circle
              key={i}
              cx={pt.x}
              cy={pt.y}
              r={3}
              fill="#8b5cf6"
              fillOpacity={0.9}
            />
          ))}

          {/* Axis labels */}
          {labelPoints.map((lp, i) => (
            <text
              key={i}
              x={lp.x}
              y={lp.y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={9}
              fill="currentColor"
              fillOpacity={0.7}
            >
              {lp.label}
            </text>
          ))}
        </svg>

        <div className="mt-4 text-center">
          <div className="text-xs text-muted-foreground">Overall Balance</div>
          <div className="text-2xl font-bold">
            {(harmony.overall_balance * 100).toFixed(0)}%
          </div>
          {harmony.overwork_consecutive_days > 0 && stage > 0 && (
            <div className="text-xs text-muted-foreground mt-1">
              {harmony.overwork_consecutive_days} consecutive day
              {harmony.overwork_consecutive_days !== 1 ? "s" : ""} overworking
            </div>
          )}
        </div>

        {/* Dimension breakdown */}
        <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {DIMENSIONS.map((d) => (
            <div key={d.key} className="flex justify-between">
              <span className="text-muted-foreground">{d.label}</span>
              <span className="font-medium">
                {(harmony.dimensions[d.key] * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
