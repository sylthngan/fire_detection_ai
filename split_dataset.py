from pathlib import Path
import random
import shutil


DATASET_DIR = Path("D-Fire")


# Cấu hình folder dataset để chia train/valid
TRAIN_IMAGES = DATASET_DIR / "train" / "images"
TRAIN_LABELS = DATASET_DIR / "train" / "labels"

VALID_IMAGES = DATASET_DIR / "valid" / "images"
VALID_LABELS = DATASET_DIR / "valid" / "labels"

#Chọn ngẫu nhiên 10% dữ liệu từ tập train để làm tập valid
VALID_RATIO = 0.10
RANDOM_SEED = 42

#Check folder valid tồn tại chưa, nếu chưa thì tạo mới
VALID_IMAGES.mkdir(parents=True, exist_ok=True)
VALID_LABELS.mkdir(parents=True, exist_ok=True)

# Lấy data 
images = list(TRAIN_IMAGES.glob("*.jpg"))
print("Total training images:", len(images))

random.seed(RANDOM_SEED)
random.shuffle(images)

# Tính số lượng ảnh validation để chia int
valid_count = int(len(images) * VALID_RATIO)
valid_images = images[:valid_count]
print("Validation images:", valid_count)

# Di chuyển ảnh và nhãn từ train sang valid
moved = 0
missing_labels = 0

for image_path in valid_images:
    label_path = TRAIN_LABELS / f"{image_path.stem}.txt"
    if not label_path.exists():
        print("WARNING - Missing label:", label_path)
        missing_labels += 1
        continue
    shutil.move(
        str(image_path),
        str(VALID_IMAGES / image_path.name)
    )
    shutil.move(
        str(label_path),
        str(VALID_LABELS / label_path.name)
    )

    moved += 1


#  kết quả
print("\nMoved images:", moved)
print("Missing labels:", missing_labels)
print("\nRemaining train images:",
      len(list(TRAIN_IMAGES.glob("*.jpg"))))

print("\nRemaining train labels:",
      len(list(TRAIN_LABELS.glob("*.txt"))))

print("\nValidation images:",
      len(list(VALID_IMAGES.glob("*.jpg"))))

print("\nValidation labels:",
      len(list(VALID_LABELS.glob("*.txt"))))
