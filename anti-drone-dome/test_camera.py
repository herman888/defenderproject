"""
InnoMaker USB camera preview for Windows.
Targets index 1 (Innomaker-U20CAM-1080PD&N-S1) — index 0 is the built-in.
Press Q to quit.
"""

import sys
import time
import cv2


INNOMAKER_INDEX = 1   # built-in is 0, InnoMaker is 1 on this machine


def open_innomaker():
    cap = cv2.VideoCapture(INNOMAKER_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"Could not open camera at index {INNOMAKER_INDEX}.")
        return None

    # MJPEG unlocks 60 fps on UVC cameras; YUYV is limited to 30 fps
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Let the IR-cut filter and auto-exposure settle
    print("Warming up camera (allow 3 s for exposure to settle)...")
    for _ in range(90):
        cap.read()
        time.sleep(0.033)

    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"InnoMaker open: {w}x{h}  {fps:.0f} fps")
    return cap


def main():
    cap = open_innomaker()
    if cap is None:
        sys.exit(1)

    print("Preview window open — press Q to quit.")
    window = "InnoMaker 1080P — Q to quit"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1280, 720)

    consecutive_blank = 0
    frame_count = 0
    fps_display = 0.0
    t0 = time.time()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("Frame read failed.")
            break

        # Warn if feed is still black after warmup
        if frame.mean() < 2.0:
            consecutive_blank += 1
            if consecutive_blank == 30:
                print("Feed looks black — check lens cap and lighting.")
        else:
            consecutive_blank = 0

        # Measure and display FPS
        frame_count += 1
        elapsed = time.time() - t0
        if elapsed >= 0.5:
            fps_display = frame_count / elapsed
            frame_count = 0
            t0 = time.time()

        cv2.putText(frame, f"FPS: {fps_display:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)

        cv2.imshow(window, frame)
        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Done.")


if __name__ == "__main__":
    main()
