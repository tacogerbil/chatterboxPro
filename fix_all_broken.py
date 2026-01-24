with open(r'ui/tabs/generation_tab.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

output = []
for i, line in enumerate(lines):
    # Fix lines that start with .CTk
    if line.strip().startswith('.CTk') and 'ctk.CTk' not in line:
        # Determine what widget type based on context
        if 'fg_color="transparent"' in line:
            line = '        ctk.CTkFrame(self.scroll_container, ' + line.strip()[5:]  # Remove .CTk,
        elif 'text=' in line:
            line = '        ctk.CTkLabel(self.scroll_container, ' + line.strip()[5:]
        elif 'command=' in line:
            line = '        ctk.CTkButton(self.scroll_container, ' + line.strip()[5:]
        else:
            line = '        ctk.CTkFrame(self.scroll_container, ' + line.strip()[5:]
        line = line + '\n'
    output.append(line)

with open(r'ui/tabs/generation_tab.py', 'w', encoding='utf-8') as f:
    f.writelines(output)

print("Fixed all broken lines")
