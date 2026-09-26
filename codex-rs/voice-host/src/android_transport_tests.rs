//! Physical capture through DSP, Opus, and a real local WebRTC receiver.
//! Captured audio is counted and discarded, never recorded or sent off-device.

use super::*;
use pretty_assertions::assert_eq;

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "requires Android microphone permission and physical audio devices"]
async fn android_microphone_reaches_webrtc_receiver() {
    timeout(Duration::from_secs(/*secs*/ 30), async {
        let (sender, mut channels) = mpsc::channel(/*buffer*/ 1);
        let gathered = Arc::new(Notify::new());
        let (media, remote_audio) = crate::audio_track::AudioTrack::new().unwrap();
        let (mut incoming, ingress) = crate::incoming::Incoming::new();
        incoming.set_suppressed(/*suppressed*/ false).unwrap();
        let mut settings = webrtc::peer_connection::SettingEngine::default();
        settings.set_lite(/*lite*/ true);
        let remote = PeerConnectionBuilder::new()
            .with_media_engine(media)
            .with_interceptor_registry(rtc::interceptor::Registry::from(ingress))
            .with_setting_engine(settings)
            .with_handler(Arc::new(RemoteEvents(sender, gathered.clone())))
            .with_udp_addrs(vec!["127.0.0.1:0"])
            .build()
            .await
            .unwrap();
        remote.add_track(remote_audio.track.clone()).await.unwrap();
        let mut local = Transport::new().await.unwrap();
        remote
            .set_remote_description(
                RTCSessionDescription::offer(local.offer().await.unwrap()).unwrap(),
            )
            .await
            .unwrap();
        let answer = remote.create_answer(/*options*/ None).await.unwrap();
        remote.set_local_description(answer).await.unwrap();
        gathered.notified().await;
        assert_eq!(
            local
                .apply_answer(remote.local_description().await.unwrap().sdp)
                .await
                .unwrap(),
            AnswerOutcome::Ready
        );
        let _channel = channels.recv().await.unwrap();
        let mut devices = crate::devices::Devices::open().unwrap();
        devices
            .set_controls(codex_realtime_webrtc::AudioControls {
                microphone_muted: false,
                speaker_suppressed: true,
            })
            .unwrap();
        let deadline = std::time::Instant::now() + Duration::from_secs(/*secs*/ 5);
        let mut sent = 0;
        let mut received = 0;
        while std::time::Instant::now() < deadline {
            sent += devices.service(&mut local.audio).await.unwrap();
            while incoming.take().unwrap().is_some() {
                received += 1;
            }
            tokio::time::sleep(Duration::from_millis(/*millis*/ 5)).await;
        }
        let state = devices.take_state().unwrap();
        eprintln!("physical capture: sent={sent}, received={received}, state={state:?}");
        drop(devices);
        local.close().await.unwrap();
        remote.close().await.unwrap();
        assert!(
            sent > 100,
            "capture/DSP did not produce sustained Opus audio"
        );
        assert!(
            received > 100,
            "WebRTC receiver did not receive captured audio"
        );
    })
    .await
    .unwrap();
}
