from litellm import models_by_provider, supports_function_calling

providers = list(models_by_provider.keys())

print(f"Total providers: {len(providers)}")
# 51

all_models = [model for models in models_by_provider.values() for model in models]

print(f"Total models: {len(all_models)}")

# Filter for models that support function calling
models_with_function_calling = [model for model in all_models if supports_function_calling(model)]

print(f"Models supporting function calling: {len(models_with_function_calling)}")
print("\nModels with function calling support:")
for model in sorted(models_with_function_calling):
    print(f"  - {model}") 
