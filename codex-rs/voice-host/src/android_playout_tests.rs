//! Explicit physical playback probe: emits a quiet tone and measures missing PCM.
//! No captured or rendered audio is saved.

use super::*;
use rtc::interceptor::Packet;
use rtc::interceptor::TaggedPacket;
use rtc::sansio::Protocol;

#[test]
#[ignore = "plays a quiet tone through the physical Android speaker"]
fn android_playout_continuity_under_capture_processing() {
    let mut encoder = opus::Encoder::new(
        /*sample_rate*/ 48_000,
        opus::Channels::Mono,
        opus::Application::Audio,
    )
    .unwrap();
    let packets: Vec<_> = (0..150u16)
        .map(|sequence| {
            let samples: Vec<_> = (0..960)
                .map(|n| {
                    ((usize::from(sequence) * 960 + n) as f32 * std::f32::consts::TAU * 440.0
                        / 48_000.0)
                        .sin()
                        * 0.08
                })
                .collect();
            let mut data = vec![0; 1275];
            let size = encoder.encode_float(&samples, &mut data).unwrap();
            data.truncate(size);
            data
        })
        .collect();
    let mut devices = Devices::open().unwrap();
    devices
        .set_controls(codex_realtime_webrtc::AudioControls {
            microphone_muted: false,
            speaker_suppressed: false,
        })
        .unwrap();
    let (mut incoming, mut ingress) = crate::incoming::Incoming::new();
    incoming.set_suppressed(/*suppressed*/ false).unwrap();
    devices
        .worker
        .buffers
        .serviced
        .store(true, Ordering::Release);
    let start = Instant::now();
    let mut sequence = 0;
    let mut measured = 0;
    let mut zeros = 0;
    let mut zero_run = 0;
    let mut longest_zero_run = 0;
    while start.elapsed() < Duration::from_millis(/*millis*/ 3200) {
        while sequence < packets.len() && start.elapsed().as_millis() >= (sequence * 20) as u128 {
            ingress
                .handle_read(TaggedPacket {
                    now: Instant::now(),
                    transport: Default::default(),
                    message: Packet::Rtp(rtc::rtp::Packet {
                        header: rtc::rtp::header::Header {
                            version: 2,
                            payload_type: crate::audio_track::OPUS_PAYLOAD_TYPE,
                            sequence_number: sequence as u16,
                            timestamp: sequence as u32 * 960,
                            ssrc: 7,
                            ..Default::default()
                        },
                        payload: packets[sequence].clone().into(),
                    }),
                })
                .unwrap();
            devices.receive(incoming.take().unwrap().unwrap()).unwrap();
            sequence += 1;
        }
        while let Some(frame) = devices.worker.buffers.rendered.pop() {
            let elapsed = frame.at.saturating_duration_since(start);
            if elapsed > Duration::from_millis(/*millis*/ 500)
                && elapsed < Duration::from_millis(/*millis*/ 2800)
            {
                for sample in &frame.samples[..frame.len] {
                    measured += 1;
                    if *sample == 0.0 {
                        zeros += 1;
                        zero_run += 1;
                        longest_zero_run = longest_zero_run.max(zero_run);
                    } else {
                        zero_run = 0;
                    }
                }
            }
            devices.worker.processor.render(&frame).unwrap();
        }
        for _ in 0..devices.worker.buffers.capture.capacity() {
            let Some(frame) = devices.worker.buffers.capture.pop() else {
                break;
            };
            devices
                .worker
                .processor
                .capture(&frame, Instant::now)
                .unwrap();
        }
        devices.take_state().unwrap();
        std::thread::sleep(Duration::from_millis(/*millis*/ 5));
    }
    eprintln!(
        "playout: packets={sequence}, measured={measured}, zeros={zeros}, longest_gap_ms={}",
        longest_zero_run as f64 / 48.0
    );
    assert!(measured > 96_000);
    assert!(
        longest_zero_run < 480,
        "speaker received gaps of at least 10 ms"
    );
}
