import re

# Read the file
with open(r'ui/tabs/generation_tab.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix pattern 1: Lines starting with spaces and .CTk
# These should be ctk.CTkLabel(self.scroll_container,
content = re.sub(
    r'^(\s+)\.CTk[^,]*,\s*text=',
    r'\1ctk.CTkLabel(self.scroll_container, text=',
    content,
    flags=re.MULTILINE
)

# Fix pattern 2: variable =.CTk, 
# These should be variable = ctk.CTkFrame(self.scroll_container,
content = re.sub(
    r'(\w+)\s*=\.CTk[^,]*,\s*fg_color=',
    r'\1 = ctk.CTkFrame(self.scroll_container, fg_color=',
    content
)

# Fix pattern 3: variable =.CTk, text=
# These should be variable = ctk.CTkLabel(self.scroll_container, text=
content = re.sub(
    r'(\w+)\s*=\.CTk[^,]*,\s*text=',
    r'\1 = ctk.CTkLabel(self.scroll_container, text=',
    content
)

# Write back
with open(r'ui/tabs/generation_tab.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed all broken lines")
