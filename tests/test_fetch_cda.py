from sgsurv.fetch_cda import find_excel_links

PAGE = "https://www.cda.gov.sg/resources/weekly-infectious-diseases-bulletin-2024/"


def test_finds_excel_links_and_ignores_pdfs():
    html = """
    <a href="https://isomer-user-content.by.gov.sg/18/abc/Weekly Infectious Disease Bulletin EW 1.pdf">EW1</a>
    <a href="https://isomer-user-content.by.gov.sg/18/4c29/weekly infectious disease bulletin_EW52-2024_upload.xlsx">Excel</a>
    <a href='/files/old-2023.xls?v=2'>old</a>
    <a href="https://isomer-user-content.by.gov.sg/18/4c29/weekly infectious disease bulletin_EW52-2024_upload.xlsx">dup</a>
    """
    links = find_excel_links(html, PAGE)
    assert links == [
        "https://isomer-user-content.by.gov.sg/18/4c29/weekly infectious disease bulletin_EW52-2024_upload.xlsx",
        "https://www.cda.gov.sg/files/old-2023.xls",
    ]


def test_unescapes_html_entities():
    html = '<a href="https://example.org/a&amp;b.xlsx">x</a>'
    assert find_excel_links(html, PAGE) == ["https://example.org/a&b.xlsx"]
