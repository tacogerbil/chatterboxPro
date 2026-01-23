import sys
sys.path.insert(0, r'a:\Coding_Projects\AI Coding\ChatterboxPro\execution\chatterboxPro')

from workers.tts_worker import get_similarity_ratio

tests = [
    ('Part one..', ' Part 1.', 'Main test case'),
    ('Chapter two', 'Chapter 2', 'Chapter number'),
    ('Part one', 'Part two', 'Different numbers'),
]

print('Testing number normalization:')
print('-' * 60)

for text1, text2, desc in tests:
    ratio = get_similarity_ratio(text1, text2)
    print(f'{desc}:')
    print(f'  Text1: {text1!r}')
    print(f'  Text2: {text2!r}')
    print(f'  Ratio: {ratio:.4f}')
    print()
