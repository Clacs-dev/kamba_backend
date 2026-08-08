"""
Geração de PDF do relatório consolidado da avaliação (secção 3.3).

Produz um PDF profissional a partir dos dados já consolidados, para a
Administração e a Assembleia Geral (como o manual descreve). Devolve os
bytes do PDF, para a rota os enviar como ficheiro.
"""
from io import BytesIO
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

# Cor institucional (o verde-azulado do KAMBA).
PRI = colors.HexColor("#356A75")
LINE = colors.HexColor("#E3E9E6")
DIM = colors.HexColor("#7C8B92")


def gerar_pdf_relatorio(report, company_name: str) -> bytes:
    """
    Recebe o objeto ConsolidatedReport (com os campos já calculados) e o nome
    da empresa, e devolve os bytes de um PDF.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Relatório Consolidado — {report.cycle_name}",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=PRI, fontSize=20, spaceAfter=4)
    eyebrow = ParagraphStyle("eyebrow", parent=styles["Normal"], textColor=DIM, fontSize=8,
                             spaceAfter=2, leading=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=PRI, fontSize=13, spaceBefore=14)
    normal = styles["Normal"]

    story = []

    # Cabeçalho
    story.append(Paragraph("KAMBA · RELATÓRIO CONSOLIDADO DE AVALIAÇÃO", eyebrow))
    story.append(Paragraph(f"{report.cycle_name}", h1))
    story.append(Paragraph(f"Empresa: {company_name}", normal))
    story.append(Paragraph(f"Gerado em {date.today().strftime('%d/%m/%Y')}", normal))
    story.append(Spacer(1, 6))

    # Resumo geral
    story.append(Paragraph("Resumo geral do ciclo", h2))
    media = report.overall_average if report.overall_average is not None else "—"
    resumo_data = [
        ["Avaliações validadas", str(report.total_validated)],
        ["Média geral", str(media)],
    ]
    for nivel, n in (report.overall_by_classification or {}).items():
        resumo_data.append([f"Classificação: {nivel}", str(n)])
    t = Table(resumo_data, colWidths=[9 * cm, 6 * cm])
    t.setStyle(_estilo_tabela())
    story.append(t)

    # Por direção
    story.append(Paragraph("Consolidação por direção", h2))
    if report.by_department:
        dep_data = [["Direção", "Avaliações", "Média", "Abaixo de 3,5"]]
        for g in report.by_department:
            dep_data.append([
                g.group, str(g.count),
                str(g.average_score if g.average_score is not None else "—"),
                str(g.below_threshold),
            ])
        t = Table(dep_data, colWidths=[7 * cm, 3 * cm, 2.5 * cm, 2.5 * cm])
        t.setStyle(_estilo_tabela(cabecalho=True))
        story.append(t)
    else:
        story.append(Paragraph("Sem dados por direção.", normal))

    # Por categoria
    story.append(Paragraph("Consolidação por categoria", h2))
    if report.by_category:
        cat_data = [["Categoria", "Avaliações", "Média"]]
        for g in report.by_category:
            cat_data.append([
                g.group, str(g.count),
                str(g.average_score if g.average_score is not None else "—"),
            ])
        t = Table(cat_data, colWidths=[8 * cm, 3.5 * cm, 3.5 * cm])
        t.setStyle(_estilo_tabela(cabecalho=True))
        story.append(t)
    else:
        story.append(Paragraph("Sem dados por categoria.", normal))

    story.append(Spacer(1, 20))
    rodape = ParagraphStyle("rodape", parent=normal, textColor=DIM, fontSize=8)
    story.append(Paragraph(
        "Documento gerado automaticamente pela plataforma KAMBA após validação pela Administração. "
        "Instrumento de apoio à Administração e à Assembleia Geral.", rodape))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _estilo_tabela(cabecalho: bool = False) -> TableStyle:
    estilos = [
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]
    if cabecalho:
        estilos += [
            ("BACKGROUND", (0, 0), (-1, 0), PRI),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    return TableStyle(estilos)
