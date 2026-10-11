
import cv2

print("Opening camera...")

cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

print("Camera opened:", cap.isOpened())

if cap.isOpened():
    print("Reading frame...")
    ret, frame = cap.read()

    print("Frame received:", ret)

    if ret and frame is not None:
        print("Frame shape:", frame.shape)

cap.release()
print("Camera released")
