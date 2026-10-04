import heapq
import os
import struct
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ==========================================
# 1. HUFFMAN TREE NODE STRUCTURE
# ==========================================
class HuffmanNode:
    def __init__(self, char, freq):
        self.char = char  # Integer byte value (0-255) or None
        self.freq = freq
        self.left = None
        self.right = None

    def __lt__(self, other):
        return self.freq < other.freq


# ==========================================
# 2. CORE COMPRESSOR / DECOMPRESSOR
# ==========================================
class HuffmanCompressor:
    def __init__(self):
        self.codes = {}
        self.freq_map = {}
        self.current_root = None

    def _build_frequency_map(self, raw_bytes):
        freq_map = {}
        for b in raw_bytes:
            freq_map[b] = freq_map.get(b, 0) + 1
        return freq_map

    def _build_huffman_tree(self, freq_map):
        heap = []
        counter = 0

        for char, freq in freq_map.items():
            node = HuffmanNode(char, freq)
            heapq.heappush(heap, (freq, counter, node))
            counter += 1

        if not heap:
            return None

        # Edge case: single unique byte
        if len(heap) == 1:
            _, _, only_node = heapq.heappop(heap)
            parent = HuffmanNode(None, only_node.freq)
            parent.left = only_node
            return parent

        while len(heap) > 1:
            _, _, node1 = heapq.heappop(heap)
            _, _, node2 = heapq.heappop(heap)

            merged = HuffmanNode(None, node1.freq + node2.freq)
            merged.left = node1
            merged.right = node2

            counter += 1
            heapq.heappush(heap, (merged.freq, counter, merged))

        return heap[0][2]

    def _generate_codes(self, node, current_code=""):
        if node is None:
            return
        if node.char is not None:
            self.codes[node.char] = current_code or "0"
            return
        self._generate_codes(node.left, current_code + "0")
        self._generate_codes(node.right, current_code + "1")

    def compress(self, input_path, output_path):
        with open(input_path, "rb") as f:
            raw_bytes = f.read()

        if not raw_bytes:
            raise ValueError("The selected file is empty.")

        self.codes.clear()
        self.freq_map = self._build_frequency_map(raw_bytes)
        self.current_root = self._build_huffman_tree(self.freq_map)
        self._generate_codes(self.current_root, "")

        # 1. Translate bitstream
        bit_chunks = [self.codes[b] for b in raw_bytes]
        encoded_bits = "".join(bit_chunks)

        pad_len = (8 - (len(encoded_bits) % 8)) % 8
        encoded_bits += "0" * pad_len

        compressed_payload = bytearray()
        for i in range(0, len(encoded_bits), 8):
            compressed_payload.append(int(encoded_bits[i:i + 8], 2))

        # 2. Extract original file extension (e.g. ".pdf", ".txt", ".png")
        _, ext = os.path.splitext(input_path)
        ext_bytes = ext.encode("utf-8")

        # 3. Compact Header Layout:
        # [1 byte: pad_len]
        # [1 byte: extension length (N)]
        # [N bytes: extension string]
        # [2 bytes: symbol count (K)]
        # K * [1 byte: raw_char, 4 bytes: frequency (uint32)]
        header = bytearray()
        header.append(pad_len)
        header.append(len(ext_bytes))
        header.extend(ext_bytes)
        header.extend(struct.pack(">H", len(self.freq_map)))

        for char_byte, freq in self.freq_map.items():
            header.extend(struct.pack(">BI", char_byte, freq))

        with open(output_path, "wb") as f:
            f.write(header)
            f.write(compressed_payload)

    def decompress(self, input_path, output_path_hint=None):
        with open(input_path, "rb") as f:
            file_data = f.read()

        if len(file_data) < 4:
            raise ValueError("Corrupt or invalid archive.")

        pad_len = file_data[0]
        ext_len = file_data[1]
        offset = 2

        orig_ext = file_data[offset:offset + ext_len].decode("utf-8", errors="ignore")
        offset += ext_len

        num_symbols = struct.unpack(">H", file_data[offset:offset + 2])[0]
        offset += 2

        self.freq_map = {}
        for _ in range(num_symbols):
            char_byte, freq = struct.unpack(">BI", file_data[offset:offset + 5])
            self.freq_map[char_byte] = freq
            offset += 5

        self.current_root = self._build_huffman_tree(self.freq_map)
        self.codes.clear()
        self._generate_codes(self.current_root, "")

        compressed_data = file_data[offset:]
        bit_string = "".join(f"{b:08b}" for b in compressed_data)
        if pad_len > 0:
            bit_string = bit_string[:-pad_len]

        decoded_bytes = bytearray()
        curr = self.current_root

        # Edge case: single repeating character
        if curr.left is not None and curr.right is None:
            char_val = curr.left.char
            decoded_bytes.extend([char_val] * curr.left.freq)
        else:
            for bit in bit_string:
                curr = curr.left if bit == "0" else curr.right
                if curr.char is not None:
                    decoded_bytes.append(curr.char)
                    curr = self.current_root

        return decoded_bytes, orig_ext


# ==========================================
# 3. INTERACTIVE HUFFMAN CODE & FREQ TABLE
# ==========================================
class CodeTableVisualizer:
    def __init__(self, parent, freq_map, codes):
        self.window = tk.Toplevel(parent)
        self.window.title("Huffman Encoding Table")
        self.window.geometry("700x520")

        # Top summary label
        total_chars = sum(freq_map.values())
        unique_chars = len(freq_map)
        orig_bits = total_chars * 8
        comp_bits = sum(freq_map[b] * len(codes[b]) for b in freq_map)
        savings = ((orig_bits - comp_bits) / orig_bits) * 100 if orig_bits > 0 else 0

        summary_text = (
            f"Unique Symbols: {unique_chars} | Total Bytes: {total_chars:,} | "
            f"Theoretical Savings: {savings:.2f}%"
        )
        tk.Label(
            self.window, text=summary_text, font=("Segoe UI", 10, "bold"),
            bg="#2c3e50", fg="#ecf0f1", pady=8
        ).pack(fill="x")

        # Treeview Table
        cols = ("byte", "char", "freq", "code", "bits")
        self.tree = ttk.Treeview(self.window, columns=cols, show="headings")

        self.tree.heading("byte", text="Byte (Dec / Hex)")
        self.tree.heading("char", text="Character")
        self.tree.heading("freq", text="Frequency (Count)")
        self.tree.heading("code", text="Huffman Code")
        self.tree.heading("bits", text="Length (Bits)")

        self.tree.column("byte", width=120, anchor="center")
        self.tree.column("char", width=100, anchor="center")
        self.tree.column("freq", width=130, anchor="e")
        self.tree.column("code", width=220, anchor="w")
        self.tree.column("bits", width=90, anchor="center")

        # Scrollbar
        scrollbar = ttk.Scrollbar(self.window, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        # Populate rows (sorted by highest frequency first)
        sorted_symbols = sorted(freq_map.items(), key=lambda x: x[1], reverse=True)
        for byte_val, freq in sorted_symbols:
            code = codes.get(byte_val, "")
            self.tree.insert("", "end", values=(
                f"{byte_val} (0x{byte_val:02X})",
                self._format_char(byte_val),
                f"{freq:,}",
                code,
                len(code)
            ))

    def _format_char(self, b):
        ch = chr(b)
        if ch == "\n": return "\\n (newline)"
        if ch == "\t": return "\\t (tab)"
        if ch == "\r": return "\\r (carriage return)"
        if ch == " ": return "' ' (space)"
        if 32 <= b <= 126: return ch
        return "[Binary / Control]"


# ==========================================
# 4. MOVABLE TREE DIAGRAM
# ==========================================
class TreeVisualizer:
    def __init__(self, parent, root_node):
        self.window = tk.Toplevel(parent)
        self.window.title("Huffman Tree Topology (Pan & Zoom)")
        self.window.geometry("1100x750")

        bar = tk.Label(
            self.window,
            text="Controls: Drag with Left Mouse to Pan | Scroll wheel or +/- to Zoom | Arrow keys / WASD to Move",
            font=("Segoe UI", 9, "bold"), bg="#2c3e50", fg="#ecf0f1", pady=6
        )
        bar.pack(fill="x", side="top")

        self.canvas = tk.Canvas(self.window, bg="#ffffff", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.root_node = root_node
        self.zoom_scale = 1.0

        # Mouse controls
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.zoom_at(1.1))
        self.canvas.bind("<Button-5>", lambda e: self.zoom_at(0.9))

        # Keyboard controls
        for key in ("<Left>", "<a>"): self.window.bind(key, lambda e: self.canvas.xview_scroll(-2, "units"))
        for key in ("<Right>", "<d>"): self.window.bind(key, lambda e: self.canvas.xview_scroll(2, "units"))
        for key in ("<Up>", "<w>"): self.window.bind(key, lambda e: self.canvas.yview_scroll(-2, "units"))
        for key in ("<Down>", "<s>"): self.window.bind(key, lambda e: self.canvas.yview_scroll(2, "units"))
        for key in ("<plus>", "<equal>"): self.window.bind(key, lambda e: self.zoom_at(1.1))
        self.window.bind("<minus>", lambda e: self.zoom_at(0.9))

        self.render_tree()

    def on_mousewheel(self, event):
        factor = 1.15 if event.delta > 0 else 0.85
        self.zoom_at(factor, event.x, event.y)

    def zoom_at(self, factor, x=None, y=None):
        if x is None: x = self.canvas.winfo_width() / 2
        if y is None: y = self.canvas.winfo_height() / 2
        new_scale = self.zoom_scale * factor
        if 0.15 < new_scale < 5.0:
            self.zoom_scale = new_scale
            self.canvas.scale("all", x, y, factor, factor)
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _measure_leaf_width(self, node):
        if node is None: return 0
        if node.left is None and node.right is None: return 1
        return self._measure_leaf_width(node.left) + self._measure_leaf_width(node.right)

    def render_tree(self):
        self.canvas.delete("all")
        if not self.root_node: return

        leaf_spacing = 65
        level_height = 80
        total_leaves = self._measure_leaf_width(self.root_node)
        canvas_needed_width = max(total_leaves * leaf_spacing + 200, 1600)

        leaf_tracker = 0
        coords = {}

        def calculate_positions(node, depth=0):
            nonlocal leaf_tracker
            if node is None: return None
            if node.left is None and node.right is None:
                x = 100 + (leaf_tracker * leaf_spacing)
                leaf_tracker += 1
                coords[id(node)] = (x, 70 + depth * level_height)
                return x

            left_x = calculate_positions(node.left, depth + 1)
            right_x = calculate_positions(node.right, depth + 1)
            x = (left_x + right_x) / 2 if (left_x and right_x) else (left_x or right_x)
            coords[id(node)] = (x, 70 + depth * level_height)
            return x

        calculate_positions(self.root_node)

        # Draw lines
        def draw_links(node):
            if not node: return
            px, py = coords[id(node)]
            if node.left:
                cx, cy = coords[id(node.left)]
                self.canvas.create_line(px, py, cx, cy, fill="#7f8c8d", width=2)
                self.canvas.create_text((px + cx)/2 - 10, (py + cy)/2, text="0", font=("Segoe UI", 9, "bold"), fill="#c0392b")
                draw_links(node.left)
            if node.right:
                cx, cy = coords[id(node.right)]
                self.canvas.create_line(px, py, cx, cy, fill="#7f8c8d", width=2)
                self.canvas.create_text((px + cx)/2 + 10, (py + cy)/2, text="1", font=("Segoe UI", 9, "bold"), fill="#27ae60")
                draw_links(node.right)

        draw_links(self.root_node)

        # Draw node circles
        r = 20
        def draw_nodes(node):
            if not node: return
            x, y = coords[id(node)]
            if node.char is not None:
                bg, border = "#e8f8f5", "#1abc9c"
                ch = chr(node.char) if 32 <= node.char <= 126 else f"0x{node.char:02X}"
                txt = f"{ch}\n{node.freq}"
            else:
                bg, border = "#ebf5fb", "#3498db"
                txt = f"Σ\n{node.freq}"

            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=bg, outline=border, width=2)
            self.canvas.create_text(x, y, text=txt, font=("Segoe UI", 8, "bold"), justify="center", fill="#2c3e50")
            draw_nodes(node.left)
            draw_nodes(node.right)

        draw_nodes(self.root_node)

        bbox = self.canvas.bbox("all")
        self.canvas.configure(scrollregion=(bbox[0] - 80, bbox[1] - 80, bbox[2] + 80, bbox[3] + 80))
        root_x, _ = coords[id(self.root_node)]
        self.canvas.xview_moveto((root_x - (1100 / 2)) / canvas_needed_width)


# ==========================================
# 5. MAIN GUI
# ==========================================
class HuffmanApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Huffman Multi-File Compressor")
        self.root.geometry("540x370")
        self.root.resizable(False, False)
        self.root.configure(bg="#f8f9fa")

        self.compressor = HuffmanCompressor()
        self.setup_ui()

    def setup_ui(self):
        title = tk.Label(
            self.root, text="Universal Huffman Compressor",
            font=("Segoe UI", 16, "bold"), fg="#2c3e50", bg="#f8f9fa"
        )
        title.pack(pady=15)

        # File Chooser
        frame_input = tk.Frame(self.root, bg="#f8f9fa")
        frame_input.pack(pady=8, fill="x", padx=25)

        self.file_entry = tk.Entry(frame_input, width=42, font=("Segoe UI", 10), bd=1, relief="solid")
        self.file_entry.pack(side="left", padx=5, ipady=4)

        browse_btn = tk.Button(
            frame_input, text="Browse", command=self.browse_file,
            font=("Segoe UI", 9, "bold"), bg="#495057", fg="white", relief="flat", padx=10
        )
        browse_btn.pack(side="left", padx=5)

        # Compress / Decompress
        btn_frame = tk.Frame(self.root, bg="#f8f9fa")
        btn_frame.pack(pady=12)

        comp_btn = tk.Button(
            btn_frame, text="🔒 Compress Any File", command=self.run_compression,
            font=("Segoe UI", 10, "bold"), bg="#2ecc71", fg="white", width=18, relief="flat", cursor="hand2", pady=5
        )
        comp_btn.pack(side="left", padx=6)

        decomp_btn = tk.Button(
            btn_frame, text="🔓 Decompress File", command=self.run_decompression,
            font=("Segoe UI", 10, "bold"), bg="#3498db", fg="white", width=18, relief="flat", cursor="hand2", pady=5
        )
        decomp_btn.pack(side="left", padx=6)

        # Visualization action triggers
        viz_frame = tk.Frame(self.root, bg="#f8f9fa")
        viz_frame.pack(pady=5)

        self.view_tree_btn = tk.Button(
            viz_frame, text="🌿 View Tree Diagram", command=self.show_visual_tree,
            font=("Segoe UI", 9, "bold"), bg="#9b59b6", fg="white", state="disabled",
            relief="flat", cursor="hand2", width=18, pady=4
        )
        self.view_tree_btn.pack(side="left", padx=6)

        self.view_table_btn = tk.Button(
            viz_frame, text="📊 View Code Table", command=self.show_code_table,
            font=("Segoe UI", 9, "bold"), bg="#e67e22", fg="white", state="disabled",
            relief="flat", cursor="hand2", width=18, pady=4
        )
        self.view_table_btn.pack(side="left", padx=6)

        # Status
        self.status_lbl = tk.Label(
            self.root, text="Ready", bd=1, relief="sunken",
            anchor="w", font=("Segoe UI", 9), bg="#e9ecef", fg="#495057", padx=8
        )
        self.status_lbl.pack(side="bottom", fill="x")

    def browse_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("All Files", "*.*")])
        if filepath:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filepath)

    def run_compression(self):
        input_path = self.file_entry.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Error", "Please select a valid input file.")
            return

        base_name = os.path.splitext(input_path)[0]
        output_path = filedialog.asksaveasfilename(
            initialfile=f"{os.path.basename(base_name)}.huff",
            defaultextension=".huff",
            filetypes=[("Huffman Archive", "*.huff")]
        )
        if not output_path:
            return

        try:
            self.status_lbl.config(text="Compressing...")
            self.root.update_idletasks()
            self.compressor.compress(input_path, output_path)

            orig_size = os.path.getsize(input_path)
            comp_size = os.path.getsize(output_path)
            savings = ((orig_size - comp_size) / orig_size) * 100 if orig_size > 0 else 0

            messagebox.showinfo(
                "Complete",
                f"Original: {orig_size:,} bytes\n"
                f"Compressed: {comp_size:,} bytes\n"
                f"Space Reduction: {savings:.2f}%"
            )
            self.status_lbl.config(text=f"Compressed. Saved: {savings:.1f}%")
            self.view_tree_btn.config(state="normal")
            self.view_table_btn.config(state="normal")
        except Exception as e:
            messagebox.showerror("Execution Error", str(e))
            self.status_lbl.config(text="Compression failed.")

    def run_decompression(self):
        input_path = self.file_entry.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Error", "Please select a valid .huff file.")
            return

        try:
            self.status_lbl.config(text="Decompressing...")
            self.root.update_idletasks()
            decoded_bytes, orig_ext = self.compressor.decompress(input_path)

            # Auto-suggest the original extension in the save dialog
            base_name = os.path.splitext(input_path)[0]
            suggested_name = f"{os.path.basename(base_name)}_extracted{orig_ext}"

            output_path = filedialog.asksaveasfilename(
                initialfile=suggested_name,
                defaultextension=orig_ext or ".*",
                filetypes=[("Restored Format", f"*{orig_ext}"), ("All Files", "*.*")]
            )
            if not output_path:
                return

            with open(output_path, "wb") as f:
                f.write(decoded_bytes)

            messagebox.showinfo("Success", f"File restored smoothly:\n{output_path}")
            self.status_lbl.config(text="Decompression successful.")
            self.view_tree_btn.config(state="normal")
            self.view_table_btn.config(state="normal")
        except Exception as e:
            messagebox.showerror("Error", f"Failed: {e}")
            self.status_lbl.config(text="Decompression failed.")

    def show_visual_tree(self):
        if self.compressor.current_root:
            TreeVisualizer(self.root, self.compressor.current_root)
        else:
            messagebox.showwarning("Warning", "No active tree loaded.")

    def show_code_table(self):
        if self.compressor.codes:
            CodeTableVisualizer(self.root, self.compressor.freq_map, self.compressor.codes)
        else:
            messagebox.showwarning("Warning", "No code data available.")


if __name__ == "__main__":
    main_window = tk.Tk()
    app = HuffmanApp(main_window)
    main_window.mainloop()