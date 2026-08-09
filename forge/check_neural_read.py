import json
d = json.load(open('/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign/student_neural_read_findings_20260808T193454Z.json'))
print('papers_read:', d['papers_read'])
print('duration_s:', d['duration_s'])
print('total_pdf_bytes:', d['total_pdf_bytes'])
print('extract_failures:', d['extract_failures'])
print('theme_counts:', d['theme_counts'])
print('cve_mentions:', d['cve_mentions'])

# Top themes by count
print('\nTop themes:')
for theme, count in sorted(d['theme_counts'].items(), key=lambda x: -x[1])[:15]:
    print(f'  {theme}: {count}')

# Sample per-paper themes
print('\nSample papers:')
for fp in d['per_paper'][:5]:
    print(f"  {fp['arxiv_id']}: {fp['themes']}")