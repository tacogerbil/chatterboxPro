import difflib
import re

text1 = 'IT TAKES MORE THAN A SALARY, MAN.'
norm1 = re.sub(r'[\W_]+', '', text1).lower()

print(f"Original: '{text1}'")
print(f"Normalized: '{norm1}'")
print(f"Length: {len(norm1)}")
print()

# Test scenarios to find what gives 0.67
scenarios = [
    ('IT TAKES MORE THAN SALARY', 'Missing: A, MAN'),
    ('IT TAKES SALARY MAN', 'Missing: MORE THAN A'),
    ('TAKES MORE THAN SALARY', 'Missing: IT, A, MAN'),
    ('IT MORE THAN SALARY', 'Missing: TAKES, A, MAN'),
    ('IT TAKES MORE SALARY', 'Missing: THAN A MAN'),
    ('TAKES MORE SALARY MAN', 'Missing: IT THAN A'),
    ('IT TAKES THAN SALARY MAN', 'Missing: MORE A'),
    ('IT TAKES MORE A SALARY', 'Missing: THAN MAN'),
]

print("Testing scenarios to find 0.67:")
print("-" * 60)

for text2, desc in scenarios:
    norm2 = re.sub(r'[\W_]+', '', text2).lower()
    ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    print(f"{desc}")
    print(f"  Transcribed: '{text2}'")
    print(f"  Ratio: {ratio:.4f}")
    if abs(ratio - 0.67) < 0.01:
        print(f"  *** MATCH! This gives ~0.67 ***")
    print()
