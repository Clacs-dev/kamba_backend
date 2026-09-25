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


def gerar_pdf_auditoria(rows: list, company_name: str) -> bytes:
    """
    Gera o PDF da trilha de auditoria, para exportar e apresentar ao Conselho
    de Administração (capítulo 7) — suporte probatório do procedimento.
    `rows` é uma lista de objetos com id, actor_name, actor_role, action,
    detail e created_at.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title="Trilha de Auditoria",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=PRI, fontSize=18, spaceAfter=4)
    eyebrow = ParagraphStyle("eyebrow", parent=styles["Normal"], textColor=DIM, fontSize=8, spaceAfter=2)
    normal = styles["Normal"]

    story = []
    story.append(Paragraph("KAMBA · TRILHA DE AUDITORIA", eyebrow))
    story.append(Paragraph("Registo imutável dos atos praticados na plataforma", h1))
    story.append(Paragraph(f"Empresa: {company_name}", normal))
    story.append(Paragraph(f"Gerado em {date.today().strftime('%d/%m/%Y')}", normal))
    story.append(Paragraph(f"Total de registos exportados: {len(rows)}", normal))
    story.append(Spacer(1, 6))

    if rows:
        dados = [["Data", "Ato", "Autor", "Perfil", "Detalhe"]]
        for r in rows:
            ts = ""
            if getattr(r, "created_at", None):
                ts = r.created_at.strftime("%d/%m/%Y %H:%M") if hasattr(r.created_at, "strftime") else str(r.created_at)
            ato = getattr(r, "action", "") or ""
            autor = getattr(r, "actor_name", "") or ""
            perfil = getattr(r, "actor_role", "") or ""
            det = (getattr(r, "detail", "") or "")[:180]
            dados.append([ts, ato, autor, perfil, det])
        t = Table(dados, colWidths=[3 * cm, 3.5 * cm, 3 * cm, 2.5 * cm, 4.5 * cm])
        t.setStyle(_estilo_tabela(cabecalho=True))
        story.append(t)
    else:
        story.append(Paragraph("Sem registos de auditoria.", normal))

    story.append(Spacer(1, 20))
    rodape = ParagraphStyle("rodape", parent=normal, textColor=DIM, fontSize=8)
    story.append(Paragraph(
        "Documento gerado automaticamente pela plataforma KAMBA. Registo imutável, "
        "carimbo temporal; destina-se ao Conselho de Administração como prova documental.", rodape))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def gerar_pdf_talento(report, company_name: str) -> bytes:
    """
    Gera o PDF da secção "Talento & Sucessão": matriz 9-Box, estrelas/risco
    de saída e o plano de sucessão por cargo-chave.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Talento & Sucessão — {report.cycle_name}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=PRI, fontSize=18, spaceAfter=4)
    eyebrow = ParagraphStyle("eyebrow", parent=styles["Normal"], textColor=DIM, fontSize=8, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=PRI, fontSize=13, spaceBefore=14)
    normal = styles["Normal"]

    ROTULAR = {
        ("alto", "alto"): "Estrela (alto p. + alto pot.)",
        ("alto", "medio"): "Alto desempenho · pot. médio",
        ("alto", "baixo"): "Alto desempenho · pot. baixo",
        ("medio", "alto"): "Alto potencial · desempenho médio",
        ("medio", "medio"): "Consistente",
        ("medio", "baixo"): "Desempenho médio · pot. baixo",
        ("baixo", "alto"): "Potencial alto · desempenho baixo",
        ("baixo", "medio"): "Em melhoria necessária",
        ("baixo", "baixo"): "Risco / plano de melhoria",
    }

    story = []
    story.append(Paragraph("KAMBA · TALENTO & SUCESSÃO", eyebrow))
    story.append(Paragraph(f"{report.cycle_name}", h1))
    story.append(Paragraph(f"Empresa: {company_name}", normal))
    story.append(Paragraph(f"Gerado em {date.today().strftime('%d/%m/%Y')}", normal))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Matriz 9-Box (desempenho × potencial)", h2))
    if report.grid:
        grid_data = [["Desempenho \\ Potencial", "Alto", "Médio", "Baixo"]]
        for perc in ("alto", "medio", "baixo"):
            linha = [perc.capitalize()]
            for pot in ("alto", "medio", "baixo"):
                n = report.grid.get(f"{perc}_{pot}", 0)
                linha.append(str(n))
            grid_data.append(linha)
        t = Table(grid_data, colWidths=[5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm])
        t.setStyle(_estilo_tabela(cabecalho=True))
        story.append(t)
        story.append(Spacer(1, 6))
        legenda = " · ".join(
            f"{ROTULAR[tuple(k.split('_'))]}: {v}" for k, v in sorted(report.grid.items())
        )
        story.append(Paragraph(legenda, normal))
    else:
        story.append(Paragraph("Sem matriz — atribua potencial no comité de talento.", normal))

    story.append(Paragraph(f"Estrelas (alto potencial + alto desempenho): {report.high_potential_count}  ·  Risco de saída assinalado: {report.risk_of_exit_count}", normal))
    story.append(Spacer(1, 4))

    story.append(Paragraph("Colaboradores avaliados", h2))
    if report.matrix:
        dados = [["Colaborador", "Desempenho", "Potencial", "Estrela", "Risco de saída"]]
        for r in report.matrix:
            dados.append([
                r.collaborator_name,
                f"{r.performance_score:.2f}" if r.performance_score is not None else "—",
                (r.potential.value if r.potential else "—"),
                "Sim" if r.is_high_potential else "",
                "Sim" if r.risk_of_exit else "",
            ])
        t = Table(dados, colWidths=[5 * cm, 3 * cm, 3 * cm, 2.5 * cm, 3 * cm])
        t.setStyle(_estilo_tabela(cabecalho=True))
        story.append(t)
    else:
        story.append(Paragraph("Sem colaboradores avaliados no ciclo.", normal))

    story.append(Paragraph("Plano de sucessão por cargo-chave", h2))
    if report.succession:
        succ_data = [["Cargo-chave", "Titular", "Sucessor", "Prontidão", "Risco de saída"]]
        for s in report.succession:
            succ_data.append([
                s.role_title,
                s.incumbent_name or "—",
                s.successor_name,
                s.readiness.value.replace("_", " ").capitalize(),
                "Sim" if s.risk_of_exit else "",
            ])
        t = Table(succ_data, colWidths=[4 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm, 2.5 * cm])
        t.setStyle(_estilo_tabela(cabecalho=True))
        story.append(t)
    else:
        story.append(Paragraph("Sem plano de sucessão definido.", normal))

    story.append(Spacer(1, 18))
    rodape = ParagraphStyle("rodape", parent=normal, textColor=DIM, fontSize=8)
    story.append(Paragraph(
        "Documento gerado automaticamente pela plataforma KAMBA. Matriz do comité de talento "
        "e plano de sucessão — instrumento de apoio à Administração.", rodape))

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


def gerar_pdf_peca_disciplinar(processo, accused_name: str, company_name: str) -> bytes:
    """
    Gera o PDF de uma peça disciplinar (nota de culpa e/ou decisão), para a
    prova documental que o manual valoriza no procedimento disciplinar.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Processo Disciplinar {processo.reference}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=PRI, fontSize=18, spaceAfter=4)
    eyebrow = ParagraphStyle("eyebrow", parent=styles["Normal"], textColor=DIM, fontSize=8, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=PRI, fontSize=12, spaceBefore=12)
    normal = styles["Normal"]

    story = []
    story.append(Paragraph("KAMBA · PROCESSO DISCIPLINAR", eyebrow))
    story.append(Paragraph(f"Processo {processo.reference}", h1))
    story.append(Paragraph(f"Empresa: {company_name}", normal))
    story.append(Paragraph(f"Arguido: {accused_name}", normal))
    story.append(Paragraph(f"Gerado em {date.today().strftime('%d/%m/%Y')}", normal))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Factos imputados", h2))
    story.append(Paragraph(processo.imputed_facts or "—", normal))

    if processo.charge_note:
        story.append(Paragraph("Nota de culpa", h2))
        story.append(Paragraph(processo.charge_note, normal))

    if processo.decision_text:
        story.append(Paragraph("Decisão", h2))
        outcome = processo.outcome.value if hasattr(processo.outcome, "value") else str(processo.outcome)
        story.append(Paragraph(f"Medida: {outcome}", normal))
        story.append(Spacer(1, 4))
        story.append(Paragraph(processo.decision_text, normal))

    story.append(Spacer(1, 20))
    rodape = ParagraphStyle("rodape", parent=normal, textColor=DIM, fontSize=8)
    story.append(Paragraph(
        "Documento gerado pela plataforma KAMBA. Peça do procedimento disciplinar, "
        "para efeitos de prova documental.", rodape))

    doc.build(story)
    buf.seek(0)
    return buf.read()
