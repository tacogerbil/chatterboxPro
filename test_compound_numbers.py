import sys
sys.path.insert(0, r'a:\Coding_Projects\AI Coding\ChatterboxPro\execution\chatterboxPro')

from workers.tts_worker import get_similarity_ratio

tests = [
    # Original test cases
    ('Part one..', ' Part 1.', 'Single digit'),
    ('Chapter two', 'Chapter 2', 'Single digit in text'),
    
    # Compound numbers
    ('twenty-three', '23', 'Hyphenated compound'),
    ('twenty three', '23', 'Space-separated compound'),
    ('ninety-nine', '99', 'High compound'),
    
    # Hundreds
    ('one hundred', '100', 'Simple hundred'),
    ('two hundred', '200', 'Multiple hundreds'),
    ('one hundred fifty', '150', 'Hundred + tens'),
    ('three hundred forty-two', '342', 'Hundred + compound'),
    
    # Thousands
    ('two thousand', '2000', 'Simple thousand'),
    ('two thousand twenty-four', '2024', 'Thousand + compound'),
    ('five thousand three hundred', '5300', 'Thousand + hundred'),
    
    # Real-world examples
    ('Chapter twenty-three', 'Chapter 23', 'Chapter number'),
    ('Page one hundred fifty-six', 'Page 156', 'Page number'),
]

print('Testing enhanced number normalization:')
print('=' * 70)

for text1, text2, desc in tests:
    ratio = get_similarity_ratio(text1, text2)
    status = '✅' if ratio == 1.0 else f'❌ ({ratio:.4f})'
    print(f'{desc:30s} {status}')
    print(f'  "{text1}" vs "{text2}"')
    print()
