import gguf

path = "models/HyperCLOVAX-SEED-Think-14B-Q4_K_M.gguf"
reader = gguf.GGUFReader(path)

field = reader.get_field('general.architecture')
if field:
    val = field.parts[0]
    if isinstance(val, bytes):
        print(f"Architecture: {val.decode('utf-8')}")
    else:
        print(f"Architecture: {val}")

print("\nFirst 20 tensors:")
for i, tensor in enumerate(reader.tensors):
    if i >= 20: break
    print(tensor.name)

print("\nFirst 20 keys:")
for i, field in enumerate(reader.fields):
    if i >= 20: break
    print(field)
