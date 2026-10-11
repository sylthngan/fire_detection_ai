import cv2

for camera_index in range(5):

    print(f"\nTesting camera index: {camera_index}")

    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print("  Cannot open")
        cap.release()
        continue

    print("  Opened")

    ret, frame = cap.read()

    if ret and frame is not None:
        print("  SUCCESS: Frame received")
        print("  Frame size:", frame.shape)

        cv2.imshow(
            f"Camera {camera_index}",
            frame
        )

        cv2.waitKey(3000)
        cv2.destroyAllWindows()

    else:
        print("  FAILED: Cannot read frame")

    cap.release()

print("\nCamera test completed.")