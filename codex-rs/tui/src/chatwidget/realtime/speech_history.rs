//! Suppress exact late captions for full answers already preserved in history.
//! Records share the bounded speech queue's count and per-item size limits.

use super::ChatWidget;
use super::MAX_PENDING_SPEECH_DELIVERIES;
use super::PendingRealtimeSpeech;
use codex_app_server_protocol::ThreadItem;

pub(super) struct RenderedSpeech {
    input_generation: u64,
    text: String,
}

impl ChatWidget {
    pub(super) fn remember_rendered_realtime_speech(&mut self, delivery: &PendingRealtimeSpeech) {
        let ThreadItem::AgentMessage { text, .. } = &delivery.item else {
            return;
        };
        let records = &mut self.realtime_conversation.rendered_speech;
        if records.len() >= MAX_PENDING_SPEECH_DELIVERIES {
            records.pop_front();
        }
        records.push_back(RenderedSpeech {
            input_generation: delivery.input_generation,
            text: text.clone(),
        });
    }

    pub(super) fn is_rendered_realtime_speech(&self, text: &str) -> bool {
        self.realtime_conversation
            .rendered_speech
            .iter()
            .any(|record| {
                record.input_generation == self.realtime_conversation.input_generation
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
