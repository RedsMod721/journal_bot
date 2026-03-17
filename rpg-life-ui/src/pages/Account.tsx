import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "@/contexts/UserContext";
import { type UserCreateRequest } from "@/services/user.service";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ---------------------------------------------------------------------------
// Timezone helpers
// ---------------------------------------------------------------------------
const TIMEZONES: string[] = (() => {
  try {
    return (Intl as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.(
      "timeZone"
    ) ?? ["UTC"];
  } catch {
    return ["UTC"];
  }
})();

const DEFAULT_TZ = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
})();

// ---------------------------------------------------------------------------
// Country helpers — build list from Intl.DisplayNames
// ---------------------------------------------------------------------------
const ISO_REGION_CODES = [
  "AD","AE","AF","AG","AI","AL","AM","AO","AQ","AR","AS","AT","AU","AW","AX","AZ",
  "BA","BB","BD","BE","BF","BG","BH","BI","BJ","BL","BM","BN","BO","BQ","BR","BS",
  "BT","BV","BW","BY","BZ","CA","CC","CD","CF","CG","CH","CI","CK","CL","CM","CN",
  "CO","CR","CU","CV","CW","CX","CY","CZ","DE","DJ","DK","DM","DO","DZ","EC","EE",
  "EG","EH","ER","ES","ET","FI","FJ","FK","FM","FO","FR","GA","GB","GD","GE","GF",
  "GG","GH","GI","GL","GM","GN","GP","GQ","GR","GS","GT","GU","GW","GY","HK","HM",
  "HN","HR","HT","HU","ID","IE","IL","IM","IN","IO","IQ","IR","IS","IT","JE","JM",
  "JO","JP","KE","KG","KH","KI","KM","KN","KP","KR","KW","KY","KZ","LA","LB","LC",
  "LI","LK","LR","LS","LT","LU","LV","LY","MA","MC","MD","ME","MF","MG","MH","MK",
  "ML","MM","MN","MO","MP","MQ","MR","MS","MT","MU","MV","MW","MX","MY","MZ","NA",
  "NC","NE","NF","NG","NI","NL","NO","NP","NR","NU","NZ","OM","PA","PE","PF","PG",
  "PH","PK","PL","PM","PN","PR","PS","PT","PW","PY","QA","RE","RO","RS","RU","RW",
  "SA","SB","SC","SD","SE","SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS",
  "ST","SV","SX","SY","SZ","TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO",
  "TR","TT","TV","TW","TZ","UA","UG","UM","US","UY","UZ","VA","VC","VE","VG","VI",
  "VN","VU","WF","WS","YE","YT","ZA","ZM","ZW",
];

const COUNTRIES: { code: string; name: string }[] = (() => {
  try {
    const regionNames = new Intl.DisplayNames(["en"], { type: "region" });
    return ISO_REGION_CODES.map((code) => ({
      code,
      name: regionNames.of(code) ?? code,
    })).sort((a, b) => a.name.localeCompare(b.name));
  } catch {
    return ISO_REGION_CODES.map((code) => ({ code, name: code }));
  }
})();

const DEFAULT_COUNTRY = (() => {
  try {
    const tag = navigator.language;
    const country = tag.split("-")[1]?.toUpperCase();
    return ISO_REGION_CODES.includes(country ?? "") ? (country ?? "FR") : "FR";
  } catch {
    return "FR";
  }
})();

// ---------------------------------------------------------------------------
// ConnectTab
// ---------------------------------------------------------------------------
function ConnectTab() {
  const { availableUsers, setUserId } = useUser();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleConnect = async (id?: string) => {
    setError(null);
    setLoading(true);
    try {
      await setUserId(id ?? value);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connect to Account</CardTitle>
        <CardDescription>Paste your user UUID to log in.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="uuid-input">User UUID</Label>
          <Input
            id="uuid-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            disabled={loading}
          />
        </div>
        <Button
          className="w-full"
          onClick={() => handleConnect()}
          disabled={loading || !value.trim()}
        >
          {loading ? "Connecting..." : "Connect"}
        </Button>

        {availableUsers.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Or pick an existing account:</p>
            <div className="flex flex-col gap-2">
              {availableUsers.map((u) => (
                <Button
                  key={u.id}
                  variant="outline"
                  className="w-full justify-start text-left"
                  onClick={() => handleConnect(u.id)}
                  disabled={loading}
                >
                  <span className="font-medium">
                    {u.display_name || u.username || u.email || `User ${u.id.slice(0, 8)}`}
                  </span>
                  <span className="ml-auto text-xs text-muted-foreground font-mono">
                    {u.id.slice(0, 8)}…
                  </span>
                </Button>
              ))}
            </div>
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// CreateAccountTab
// ---------------------------------------------------------------------------
function CreateAccountTab() {
  const { createUser } = useUser();
  const navigate = useNavigate();

  const [form, setForm] = useState<UserCreateRequest>({
    password: "",
    email: "",
    username: "",
    display_name: "",
    timezone: DEFAULT_TZ,
    home_country: DEFAULT_COUNTRY,
    enable_tutorial: true,
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const update = (field: keyof UserCreateRequest, value: string | boolean) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((form.password ?? "").length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const payload: UserCreateRequest = {
        password: form.password,
        email: form.email || undefined,
        username: form.username || undefined,
        display_name: form.display_name || undefined,
        timezone: form.timezone || "UTC",
        home_country: (form.home_country || "FR").toUpperCase(),
        enable_tutorial: form.enable_tutorial,
      };
      await createUser(payload);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create account");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create Account</CardTitle>
        <CardDescription>Start your RPG life journey.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Password — required */}
          <div className="space-y-2">
            <Label htmlFor="password">Password *</Label>
            <Input
              id="password"
              type="password"
              value={form.password}
              onChange={(e) => update("password", e.target.value)}
              placeholder="Min 8 characters"
              required
              disabled={loading}
            />
          </div>

          {/* Username */}
          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              value={form.username ?? ""}
              onChange={(e) => update("username", e.target.value)}
              placeholder="Optional, max 50 chars"
              maxLength={50}
              disabled={loading}
            />
          </div>

          {/* Display Name */}
          <div className="space-y-2">
            <Label htmlFor="display_name">Display Name</Label>
            <Input
              id="display_name"
              value={form.display_name ?? ""}
              onChange={(e) => update("display_name", e.target.value)}
              placeholder="Optional, max 100 chars"
              maxLength={100}
              disabled={loading}
            />
          </div>

          {/* Email — optional */}
          <div className="space-y-2">
            <Label htmlFor="email">Email <span className="text-muted-foreground text-xs">(optional)</span></Label>
            <Input
              id="email"
              type="email"
              value={form.email ?? ""}
              onChange={(e) => update("email", e.target.value)}
              placeholder="Leave blank to auto-generate"
              disabled={loading}
            />
          </div>

          {/* Timezone — dropdown */}
          <div className="space-y-2">
            <Label htmlFor="timezone">Timezone</Label>
            <Select
              value={form.timezone}
              onValueChange={(v) => update("timezone", v)}
              disabled={loading}
            >
              <SelectTrigger id="timezone">
                <SelectValue placeholder="Select timezone" />
              </SelectTrigger>
              <SelectContent className="max-h-60">
                {TIMEZONES.map((tz) => (
                  <SelectItem key={tz} value={tz}>
                    {tz}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Home Country — dropdown */}
          <div className="space-y-2">
            <Label htmlFor="home_country">Home Country</Label>
            <Select
              value={form.home_country}
              onValueChange={(v) => update("home_country", v)}
              disabled={loading}
            >
              <SelectTrigger id="home_country">
                <SelectValue placeholder="Select country" />
              </SelectTrigger>
              <SelectContent className="max-h-60">
                {COUNTRIES.map(({ code, name }) => (
                  <SelectItem key={code} value={code}>
                    {name} ({code})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Tutorial Mode — toggle */}
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="tutorial-mode" className="text-base cursor-pointer">
                Tutorial Mode
              </Label>
              <p className="text-sm text-muted-foreground">
                Enables the tutorial arc and guided learning phase
              </p>
            </div>
            <Switch
              id="tutorial-mode"
              checked={form.enable_tutorial ?? true}
              onCheckedChange={(checked) => update("enable_tutorial", checked)}
              disabled={loading}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button type="submit" className="w-full" disabled={loading || !form.password}>
            {loading ? "Creating..." : "Create Account"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Account page
// ---------------------------------------------------------------------------
export function Account() {
  const { user, isLoading } = useUser();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && user) navigate("/", { replace: true });
  }, [user, isLoading, navigate]);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-bold">RPG Life</h1>
          <p className="text-muted-foreground">Your gamified life tracker</p>
        </div>

        <Tabs defaultValue="connect">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="connect">Connect</TabsTrigger>
            <TabsTrigger value="create">Create Account</TabsTrigger>
          </TabsList>
          <TabsContent value="connect">
            <ConnectTab />
          </TabsContent>
          <TabsContent value="create">
            <CreateAccountTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
