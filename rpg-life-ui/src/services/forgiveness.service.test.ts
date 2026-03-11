import { forgivenessService } from "@/services/forgiveness.service";

const { getMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    defaults: {
      baseURL: "http://localhost:8000",
    },
    get: getMock,
    post: postMock,
  },
  apiPath: (path: string) => `/api${path}`,
}));

describe("forgivenessService", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("falls back to localhost:8001 when localhost:8000 returns 404 for config", async () => {
    getMock
      .mockResolvedValueOnce({
        status: 404,
        data: { detail: "Not Found" },
      })
      .mockResolvedValueOnce({
        status: 200,
        data: {
          preset: "balanced",
          skill_decay_rate: 0.05,
          skill_grace_period_days: 7,
          insight_decay_rate: 0.1,
          insight_grace_period_days: 3,
          critical_staleness_threshold: 0.8,
        },
      });

    const result = await forgivenessService.getConfig("user-1");

    expect(getMock).toHaveBeenCalledTimes(2);
    expect(getMock).toHaveBeenNthCalledWith(
      1,
      "/api/forgiveness/config",
      expect.objectContaining({
        params: { user_id: "user-1" },
        validateStatus: expect.any(Function),
      }),
    );
    expect(getMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8001/api/forgiveness/config",
      expect.objectContaining({
        params: { user_id: "user-1" },
        validateStatus: expect.any(Function),
      }),
    );
    expect(result.preset).toBe("balanced");
  });

  it("falls back to localhost:8001 when localhost:8000 returns 404 for preset updates", async () => {
    postMock
      .mockResolvedValueOnce({
        status: 404,
        data: { detail: "Not Found" },
      })
      .mockResolvedValueOnce({
        status: 200,
        data: {
          preset: "custom",
          skill_decay_rate: 0.05,
          skill_grace_period_days: 7,
          insight_decay_rate: 0.1,
          insight_grace_period_days: 3,
          critical_staleness_threshold: 0.8,
        },
      });

    const result = await forgivenessService.updatePreset("user-1", "custom");

    expect(postMock).toHaveBeenCalledTimes(2);
    expect(postMock).toHaveBeenNthCalledWith(
      1,
      "/api/forgiveness/config/preset",
      { preset: "custom" },
      expect.objectContaining({
        params: { user_id: "user-1" },
        validateStatus: expect.any(Function),
      }),
    );
    expect(postMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8001/api/forgiveness/config/preset",
      { preset: "custom" },
      expect.objectContaining({
        params: { user_id: "user-1" },
        validateStatus: expect.any(Function),
      }),
    );
    expect(result.preset).toBe("custom");
  });
});
