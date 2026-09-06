# Chinese alias evidence review — 2026-09-06

The primary artifact is the filing-anchored alias library. This batch reviews names,
not live filing eligibility or exhaustive trial-site coverage. Filing anchors remain
the 2026-09-05 snapshot; new source access dates are 2026-09-06.

## Approved

- Nantong: the university report explicitly identifies the Second Affiliated Hospital
  as Nantong First People's Hospital and dates its former affiliated name to
  1992–2004. Both names are added to that filing only.
  Source: https://ntdxxb.ntu.edu.cn/2017/0301/c2453a56107/page.htm
- Hangzhou: the Westlake unveiling report supports the medical-school-qualified
  hospital name. The literal filing canonical name is unchanged.
  Source: https://medicine.westlake.edu.cn/News/202311/t20231120_35311.shtml
- Shuangliu: the hospital-authored university employer profile explicitly records
  adoption of the airport-hospital name on 2020-03-18. West China Hospital remains
  a separate identity; management cooperation does not merge filings.
  Source: https://jy.scu.edu.cn/index/index/employjobdetail.html?data=MDAwMDAwMDAwMJG6n3_Ed6imi4qQtLh4iZmKz7ausnbddricp9CWi5qikaeWacSdqLqGfaK2w4iil5C4zNbGiL-E

## Investigated, not approved in this batch

- 河南中医学院第一医院: university search results use 第一附属医院 instead;
  the exact candidate has not been substantiated. Do not silently insert 附属.
- 广东药学院第一附属医院: government leads use 附属第一医院 instead. A secondary
  directory's rename narrative is insufficient to approve the exact candidate.
- 武汉普爱医院: the health commission co-lists 武汉市普爱医院. The shorter candidate
  still requires exact-name corroboration.
  Lead: https://wjw.wuhan.gov.cn/zwgk_28/fdzdgknr/xkfw/spgg/202204/t20220408_1952550.shtml
- 顺德第二人民医院: the hospital website search index explicitly co-lists it, but
  direct retrieval timed out twice. Retain pending until readable primary evidence.
  Lead: https://www.sddermyy.com/newsinfo/8038146.html

This is not a negative identity determination for the retained names. Search
absence, wording differences, and retrieval failures are evidence gaps only.

## Reproducible checks

### Follow-up: rename approvals and exact spellings

- Approved 中国科学院大学宁波华美医院 as a historical name of 宁波市第二医院.
  The primary approval is 浙卫发函〔2022〕183号, signed 2022-12-23, posted
  2023-01-09, index 002482365/2022-08107. It requires subsequent change
  registration, so neither date is copied into `valid_to`.
  Source: https://wsjkw.zj.gov.cn/art/2023/1/9/art_1229123470_59019349.html
- Approved 汉口普爱医院, documented hospital history 1864–1958.
  Source: https://www.puaihospital.cn/list/2.html
- The earlier 武汉普爱医院 evidence gap is now resolved: the hospital's own
  2016-12-21 notice uses the exact name in its HR signature. Approved as a short
  name, without inventing a validity interval. Direct HTML retrieval succeeded
  after the browsing tool reported a cache miss; only the relevant institution
  wording is retained here, not applicant information.
  Source: https://www.puaihospital.cn/view/14.html
- Repeat exact-name searches did not resolve 河南中医学院第一医院 or
  广东药学院第一附属医院. Both remain unapproved, not rejected identities.

This follow-up adds three names for two existing filings, resolves two queued
candidate records, and discovers one additional historical name. It does not
refresh the filing snapshot or certify all reported trial-center identities.

Run the build, independent official-alias check, reviewed-site refresh, unit tests,
and the code cells in `notebooks/official-alias-quality.ipynb`. Regression tests
protect separate managing-hospital identities, literal filing names, and historical
date precision. No English names are approved by this batch.
