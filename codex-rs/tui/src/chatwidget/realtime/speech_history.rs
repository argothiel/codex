//! Publish completed voice answers independently of speech delivery.
//! Suppress exact late captions for full answers already preserved in history.
//! Records share the bounded speech queue's count and per-item size limits.

use super::ChatWidget;
use super::MAX_PENDING_SPEECH_DELIVERIES;
use super::PendingRealtimeSpeech;
use super::RealtimeAgentItemOrigin;
use super::can_retain_realtime_speech;
use super::is_private_realtime_agent_item;
use crate::app_event::AppEvent;
use crate::chatwidget::ThreadItemRenderSource;
use codex_app_server_protocol::ThreadItem;

pub(super) struct RenderedSpeech {
    input_generation: u64,
    text: String,
}

impl ChatWidget {
    pub(in crate::chatwidget) fn publish_completed_realtime_delegation(
        &mut self,
        turn_id: &str,
        item: &ThreadItem,
    ) {
        let Some(RealtimeAgentItemOrigin::Delegated {
            completed: true,
            suppressed_nonfinal,
            ..
        }) = self
            .realtime_conversation
            .agent_items
            .get(&(turn_id.to_string(), item.id().to_string()))
        else {
            return;
        };
        if is_private_realtime_agent_item(item) {
            return;
        }
        let pending = self
            .realtime_conversation
            .pending_speech
            .iter_mut()
            .find(|pending| pending.turn_id == turn_id && pending.item.id() == item.id());
        match pending {
            Some(pending) if !pending.published => pending.published = true,
            None if *suppressed_nonfinal => {}
            Some(_) | None => return,
        }
        // Publish the authoritative turn result before scheduling speech. Keep
        // delegation ownership intact so audio can still be routed separately.
        for cell in self.take_realtime_transcript_history() {
            self.app_event_tx.send(AppEvent::InsertHistoryCell(cell));
        }
        self.remember_rendered_realtime_answer(
            turn_id,
            item,
            self.realtime_conversation.input_generation,
        );
        self.handle_thread_item(
            item.clone(),
            turn_id.to_string(),
            ThreadItemRenderSource::RealtimeAnswer,
        );
    }

    pub(super) fn remember_rendered_realtime_speech(&mut self, delivery: &PendingRealtimeSpeech) {
        self.remember_rendered_realtime_answer(
            &delivery.turn_id,
            &delivery.item,
            delivery.input_generation,
        );
    }

    fn remember_rendered_realtime_answer(
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
