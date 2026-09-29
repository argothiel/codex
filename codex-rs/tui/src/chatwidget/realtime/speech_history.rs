//! Remember displayed voice answers without changing audio delivery state.

use super::ChatWidget;
use super::MAX_PENDING_SPEECH_DELIVERIES;
use super::can_retain_realtime_speech;
use codex_app_server_protocol::ThreadItem;

pub(super) struct RenderedSpeech {
    input_generation: u64,
    text: String,
}

impl ChatWidget {
    pub(super) fn remember_rendered_realtime_answer(
        &mut self,
        turn_id: &str,
        item: &ThreadItem,
        input_generation: u64,
    ) {
        if !can_retain_realtime_speech(turn_id, item) {
            return;
        }
        let ThreadItem::AgentMessage { text, .. } = item else {
            return;
        };
        let records = &mut self.realtime_conversation.rendered_speech;
        if records.len() >= MAX_PENDING_SPEECH_DELIVERIES {
            records.pop_front();
        }
        records.push_back(RenderedSpeech {
            input_generation,
            text: text.clone(),
        });
    }

    pub(super) fn is_rendered_realtime_speech(&self, text: &str) -> bool {
        let input_generation = self
            .realtime_conversation
            .assistant_transcript_generation
            .unwrap_or(self.realtime_conversation.input_generation);
        self.realtime_conversation
            .rendered_speech
            .iter()
            .any(|record| {
                record.input_generation == input_generation
                    && record
                        .text
                        .trim()
                        .strip_prefix("[FINAL]")
                        .unwrap_or(record.text.trim())
                        .split_whitespace()
                        .eq(text.split_whitespace())
            })
    }
}
