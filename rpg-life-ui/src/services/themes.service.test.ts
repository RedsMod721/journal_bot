import { themesService } from "@/services/themes.service";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    defaults: {
      baseURL: "http://localhost:8000",
    },
    get: getMock,
  },
  apiPath: (path: string) => `/api${path}`,
}));

describe("themesService", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("falls back to localhost:8002 when localhost:8000 omits related skill names", async () => {
    getMock
      .mockResolvedValueOnce({
        data: [
          {
            theme_id: "theme-1",
            user_id: "user-1",
            name: "Physical",
            total_xp: 100,
            current_level: 1,
            current_level_xp: 0,
            next_level_xp: 100,
            related_skills_count: 2,
            created_at: "2026-03-11T00:00:00Z",
            updated_at: "2026-03-11T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        data: [
          {
            theme_id: "theme-1",
            user_id: "user-1",
            name: "Physical",
            total_xp: 100,
            current_level: 1,
            current_level_xp: 0,
            next_level_xp: 100,
            related_skills_count: 2,
            related_skill_names: ["Running", "Mobility"],
            created_at: "2026-03-11T00:00:00Z",
            updated_at: "2026-03-11T00:00:00Z",
          },
        ],
      });

    const result = await themesService.getThemes("user-1");

    expect(getMock).toHaveBeenCalledTimes(2);
    expect(getMock).toHaveBeenNthCalledWith(1, "/api/themes", {
      params: { user_id: "user-1" },
    });
    expect(getMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8002/api/themes",
      { params: { user_id: "user-1" } }
    );
    expect(result[0].related_skill_names).toEqual(["Running", "Mobility"]);
  });

  it("keeps the primary response when related skill names are already present", async () => {
    getMock.mockResolvedValueOnce({
      data: [
        {
          theme_id: "theme-1",
          user_id: "user-1",
          name: "Physical",
          total_xp: 100,
          current_level: 1,
          current_level_xp: 0,
          next_level_xp: 100,
          related_skills_count: 1,
          related_skill_names: ["Running"],
          created_at: "2026-03-11T00:00:00Z",
          updated_at: "2026-03-11T00:00:00Z",
        },
      ],
    });

    const result = await themesService.getThemes("user-1");

    expect(getMock).toHaveBeenCalledTimes(1);
    expect(result[0].related_skill_names).toEqual(["Running"]);
  });
});
