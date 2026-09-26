//! Explicit on-device checks. These open the microphone but never save captured audio.

use super::*;

#[test]
#[ignore = "requires Android microphone permission and physical audio devices"]
fn android_duplex_capture_timing_and_mute() {
    assert!(cpal::default_host().devices().unwrap().next().is_some());
    let mut devices = Devices::open().expect("open Android microphone and speaker");
    devices
        .set_controls(codex_realtime_webrtc::AudioControls {
            microphone_muted: false,
            speaker_suppressed: false,
        })
        .unwrap();
    let buffers = devices.worker.buffers.clone();
    buffers.serviced.store(true, Ordering::Release);
    let deadline = Instant::now() + Duration::from_secs(/*secs*/ 2);
    let mut captured = 0;
    let mut rendered = 0;
    while Instant::now() < deadline {
        while let Some(frame) = buffers.capture.pop() {
            assert!(frame.at <= Instant::now());
            assert!(frame.at.elapsed() < MAX_CAPTURE_AGE);
            assert!(
                frame.samples[..frame.len]
                    .iter()
                    .all(|sample| sample.is_finite())
            );
            captured += frame.len;
        }
        while let Some(frame) = buffers.rendered.pop() {
            rendered += frame.len;
        }
        devices.take_state().unwrap();
        std::thread::sleep(Duration::from_millis(/*millis*/ 5));
    }
    assert!(
        captured > 48_000,
        "capture callbacks stopped or timestamps were rejected"
    );
    assert!(rendered > 48_000, "speaker callbacks stopped");
    devices
        .set_controls(codex_realtime_webrtc::AudioControls {
            microphone_muted: true,
            speaker_suppressed: true,
        })
        .unwrap();
    std::thread::sleep(Duration::from_millis(/*millis*/ 100));
    while buffers.capture.pop().is_some() {}
    std::thread::sleep(Duration::from_millis(/*millis*/ 100));
    assert!(
        buffers.capture.is_empty(),
        "muted microphone enqueued audio"
    );
    let unmuted_at = Instant::now();
    devices
        .set_controls(codex_realtime_webrtc::AudioControls {
            microphone_muted: false,
            speaker_suppressed: true,
        })
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(/*secs*/ 2);
    let frame = loop {
        if let Some(frame) = buffers.capture.pop() {
            break frame;
        }
        assert!(
            Instant::now() < deadline,
            "capture did not resume after unmute"
        );
        std::thread::sleep(Duration::from_millis(/*millis*/ 5));
    };
    assert!(
        frame.at >= unmuted_at,
        "pre-unmute audio escaped the capture cutoff"
    );
    drop(devices);
    let reopened = Devices::open().expect("devices released after close");
    drop(reopened);
}
