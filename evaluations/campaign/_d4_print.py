with open("evaluations/campaign/rbs_v4_final_report.md") as f:
    txt = f.read()
# Print section 27 Reproducibility Information
i = txt.find("## 27. Reproducibility Information")
if i >= 0:
    print(txt[i:i+1500])