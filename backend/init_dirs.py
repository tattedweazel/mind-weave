import os

# Create missing packages as a single run
os.makedirs("app/api/v1", exist_ok=True)
os.makedirs("app/core", exist_ok=True)
os.makedirs("app/domain/services", exist_ok=True)
os.makedirs("app/persistence/repos", exist_ok=True)
os.makedirs("app/providers", exist_ok=True)
os.makedirs("app/prompting", exist_ok=True)

# Add __init__.py files
open("app/__init__.py", "a").close()
open("app/api/__init__.py", "a").close()
open("app/api/v1/__init__.py", "a").close()
open("app/core/__init__.py", "a").close()
open("app/domain/__init__.py", "a").close()
open("app/domain/services/__init__.py", "a").close()
open("app/persistence/__init__.py", "a").close()
open("app/persistence/repos/__init__.py", "a").close()
open("app/providers/__init__.py", "a").close()
open("app/prompting/__init__.py", "a").close()
