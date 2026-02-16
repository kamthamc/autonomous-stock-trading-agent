try:
    print("Importing google.generativeai...")
    import google.generativeai
    print("Success")
    print("Importing PIL...")
    import PIL.Image
    print("Success")
    print("Importing pydantic...")
    import pydantic
    print("Success")
    print("Importing pydantic_settings...")
    import pydantic_settings
    print("Success")
except Exception as e:
    print(f"Failed: {e}")
