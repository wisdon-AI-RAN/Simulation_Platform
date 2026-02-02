import os
import csv
import xml.etree.ElementTree as ET

def extract_bounding_box_from_gml(gml_file_path):
    """
    從 GML 檔案中解析 <gml:lowerCorner> 與 <gml:upperCorner> 的文字，並回傳成 tuple。
    若找不到則回傳 (None, None)。
    """
    try:
        tree = ET.parse(gml_file_path)
        root = tree.getroot()

        # 一般 GML 的命名空間
        ns = {
            'gml': 'http://www.opengis.net/gml'
        }

        # 尋找 <gml:boundedBy> -> <gml:Envelope> -> <gml:lowerCorner> 和 <gml:upperCorner>
        lower_corner_elem = root.find('.//gml:boundedBy/gml:Envelope/gml:lowerCorner', ns)
        upper_corner_elem = root.find('.//gml:boundedBy/gml:Envelope/gml:upperCorner', ns)

        if lower_corner_elem is not None and upper_corner_elem is not None:
            lower_corner = lower_corner_elem.text.strip()
            upper_corner = upper_corner_elem.text.strip()
            return lower_corner, upper_corner
        else:
            return None, None

    except ET.ParseError:
        return None, None

def main():
    # 三個放置 GML 檔案的資料夾（Windows 路徑記得使用 r'' raw string 或替換成兩條反斜線 \\）
    directories = [
        r"C:\Users\zihao\Desktop\台固\三維建物圖資\融合版GML\111_E_BUILD\gml",
        r"C:\Users\zihao\Desktop\台固\三維建物圖資\融合版GML\111_F_BUILD\gml",
        r"C:\Users\zihao\Desktop\台固\三維建物圖資\融合版GML\112_O_OK\gml"
    ]

    # 輸出的 CSV 檔案名稱
    output_csv = "gml_bounding_boxes.csv"

    # 先蒐集所有 .gml 檔案，才可預先知道總數來顯示進度
    gml_files = []
    for directory in directories:
        if os.path.isdir(directory):
            for root_dir, _, files in os.walk(directory):
                for file_name in files:
                    if file_name.lower().endswith(".gml"):
                        gml_files.append(os.path.join(root_dir, file_name))
        else:
            print(f"資料夾不存在或路徑錯誤: {directory}")

    total_files = len(gml_files)
    print(f"找到 {total_files} 個 GML 檔案，開始解析...")

    # 開啟 CSV，寫入標頭
    with open(output_csv, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # 欄位名稱
        writer.writerow(["Filename", "LowerCorner", "UpperCorner"])

        # 遍歷所有 GML 檔案
        for idx, gml_path in enumerate(gml_files, start=1):
            # 解析 GML 檔
            lower, upper = extract_bounding_box_from_gml(gml_path)

            # 寫入 CSV
            writer.writerow([os.path.basename(gml_path), lower, upper])

            # 印出目前進度
            print(f"[{idx}/{total_files}] 已處理：{os.path.basename(gml_path)}")

    print("所有檔案處理完成，CSV 寫入完成！")
    print(f"輸出檔案：{output_csv}")

if __name__ == "__main__":
    main()
