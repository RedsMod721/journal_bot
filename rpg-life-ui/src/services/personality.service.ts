import apiClient, { apiPath } from "@/lib/api";

export const PERSONALITY_IDS = [
  "observer",
  "therapist",
  "coach",
  "sassy",
  "wargod",
  "raphael",
] as const;

export type PersonalityId = (typeof PERSONALITY_IDS)[number];
export type LikabilityScores = Record<PersonalityId, number>;

export interface PersonalityStateResponse {
  active_personality: PersonalityId;
  likability_scores: LikabilityScores;
  switch_cooldown_seconds: number;
  multi_personality_annotations: number;
}

export interface PersonalityMessageResponse {
  id: string;
  entry_id: string;
  personality: PersonalityId | "system";
  message_type: string;
  message_text: string;
  logical_slot_key: string;
  context_data: Record<string, unknown>;
  multi_personality: {
    is_primary: boolean;
    primary_personality: PersonalityId | string;
    impact_multiplier: number;
  };
  created_at: string;
}

export interface PersonalityFeedbackPayload {
  message_id: string;
  feedback_type: "thumbs_up" | "thumbs_down" | "explicit_positive" | "explicit_negative";
}

export interface PersonalityFeedbackResponse {
  personality: PersonalityId;
  old_likability: number;
  new_likability: number;
  delta: number;
  impact_multiplier: number;
}

export interface UpdateLikabilityScoresPayload {
  likability_scores: LikabilityScores;
}

export const personalityService = {
  getState: async (userId: string): Promise<PersonalityStateResponse> => {
    const { data } = await apiClient.get(apiPath("/personality/state"), {
      params: { user_id: userId },
    });
    return data;
  },

  getMessages: async (
    userId: string,
    entryId?: string,
    limit = 50
  ): Promise<PersonalityMessageResponse[]> => {
    const { data } = await apiClient.get(apiPath("/personality/messages"), {
      params: { user_id: userId, entry_id: entryId, limit },
    });
    return data;
  },

  submitFeedback: async (
    userId: string,
    payload: PersonalityFeedbackPayload
  ): Promise<PersonalityFeedbackResponse> => {
    const { data } = await apiClient.post(apiPath("/personality/feedback"), payload, {
      params: { user_id: userId },
    });
    return data;
  },

  updateLikabilityScores: async (
    userId: string,
    likabilityScores: LikabilityScores
  ): Promise<PersonalityStateResponse> => {
    const { data } = await apiClient.patch(
      apiPath("/personality/state"),
      { likability_scores: likabilityScores },
      {
        params: { user_id: userId },
      }
    );
    return data;
  },
};
