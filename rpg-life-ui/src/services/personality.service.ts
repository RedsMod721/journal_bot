import apiClient, { apiPath } from "@/lib/api";

export interface PersonalityStateResponse {
  active_personality: string;
  likability_scores: Record<string, number>;
  switch_cooldown_seconds: number;
  multi_personality_annotations: number;
}

export interface PersonalityMessageResponse {
  id: string;
  entry_id: string;
  personality: string;
  message_type: string;
  message_text: string;
  context_data: Record<string, unknown>;
  created_at: string;
}

export interface PersonalityFeedbackPayload {
  message_id: string;
  feedback_type: "thumbs_up" | "thumbs_down" | "explicit_positive" | "explicit_negative";
}

export interface PersonalityFeedbackResponse {
  personality: string;
  old_likability: number;
  new_likability: number;
  delta: number;
  impact_multiplier: number;
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
    limit = 5
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
};
