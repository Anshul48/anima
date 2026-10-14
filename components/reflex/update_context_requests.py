import os
import re

def main():
    test_dir = os.path.join(os.path.dirname(__file__), "tests")
    for root, _, files in os.walk(test_dir):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
            
            # Replace basic ContextRequest
            new_content = re.sub(
                r'ContextRequest\(\s*session_id="[^"]*"(?:,\s*query="[^"]*")?(?:,\s*timeout_ms=[0-9.]+)?\s*\)',
                'ContextRequest(request_id="test", consumer_identity="test", purpose="ASSISTED", scopes=[], deadline_ms=100, freshness_ms=100, budget_tokens=10)',
                content
            )

            # Replace ContextRequest in test_integration_security_and_failure
            new_content = re.sub(
                r'ContextRequest\(\s*session_id=[^,]+,\s*query=[^)]+\)',
                'ContextRequest(request_id="test", consumer_identity="test", purpose="ASSISTED", scopes=[], deadline_ms=100, freshness_ms=100, budget_tokens=10)',
                new_content
            )
            
            # Change get_context_snapshot to get_context
            new_content = new_content.replace('get_context_snapshot(', 'get_context(')
            
            if content != new_content:
                with open(path, "w", encoding="utf-8") as file:
                    file.write(new_content)
                print(f"Updated {f}")

if __name__ == "__main__":
    main()
