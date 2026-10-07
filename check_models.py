import google.generativeai as genai


genai.configure(api_key=api_key)

print("🔍 contacting Google to check your account permissions...")

try:
    print("\n✅ AVAILABLE MODELS FOR YOU:")
    print("-" * 30)
    found_any = False
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f" • {m.name}")
            found_any = True
    
    if not found_any:
        print("❌ No models found! Your API Key might be invalid or has no access.")
    print("-" * 30)

except Exception as e:
    print(f"\n❌ CRITICAL ERROR: {e}")
