import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import torch
print("PyTorch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    free, total = torch.cuda.mem_get_info(0)
    print(f"VRAM: {free/1e9:.1f} GB free / {total/1e9:.1f} GB total")
else:
    print("No CUDA GPU detected")
