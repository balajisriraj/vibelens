import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { Video } from "../api";

export type PlayerHandle = { seek: (t: number) => void };

/**
 * One interface over two players. YouTube is driven through the IFrame API's postMessage protocol
 * (no extra script), local media through a plain <video>. Both report the current time upward.
 */
export const Player = forwardRef<PlayerHandle, { video: Video; onTime: (t: number) => void }>(function Player(
  { video, onTime },
  ref,
) {
  const frame = useRef<HTMLIFrameElement>(null);
  const media = useRef<HTMLVideoElement>(null);
  const youtube = video.kind === "youtube";

  const command = (func: string, args: unknown[] = []) =>
    frame.current?.contentWindow?.postMessage(JSON.stringify({ event: "command", func, args }), "*");

  useImperativeHandle(ref, () => ({
    seek: (t: number) => {
      if (youtube) {
        command("seekTo", [t, true]);
        command("playVideo");
      } else if (media.current) {
        media.current.currentTime = t;
        void media.current.play().catch(() => {});
      }
      onTime(t);
    },
  }));

  useEffect(() => {
    if (!youtube) return;
    const listen = () => frame.current?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: video.id }), "*");
    const onMessage = (e: MessageEvent) => {
      if (!/youtube(-nocookie)?\.com$/.test(new URL(e.origin).hostname)) return;
      try {
        const data = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
        const t = data?.info?.currentTime;
        if (typeof t === "number") onTime(t);
      } catch {
        /* not ours */
      }
    };
    addEventListener("message", onMessage);
    const el = frame.current;
    el?.addEventListener("load", listen);
    return () => {
      removeEventListener("message", onMessage);
      el?.removeEventListener("load", listen);
    };
  }, [youtube, video.id, onTime]);

  if (youtube)
    return (
      <div className="screen">
        <iframe
          ref={frame}
          src={`https://www.youtube-nocookie.com/embed/${video.ref}?enablejsapi=1&rel=0&modestbranding=1&origin=${encodeURIComponent(location.origin)}`}
          title={video.title}
          allow="accelerometer; autoplay; encrypted-media; picture-in-picture"
          allowFullScreen
        />
      </div>
    );
  if (video.kind === "captions")
    return (
      <div className="screen empty">
        <b>Captions only</b>
        <span>No media was uploaded, so timestamps scroll the transcript instead of a player.</span>
      </div>
    );
  return (
    <div className="screen">
      <video ref={media} src={`/api/videos/${video.id}/media`} controls preload="metadata" onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)}>
        <track kind="captions" src={`/api/videos/${video.id}/transcript.vtt`} srcLang="en" label="English" />
      </video>
    </div>
  );
});
