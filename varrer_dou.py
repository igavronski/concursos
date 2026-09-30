import zipfile
import xml.etree.ElementTree as ET
import re
import io
import requests
import argparse
import sys
from datetime import date, timedelta

def processar_xml_conteudo(conteudo_xml, palavras_chave, nome_arquivo):
    """Aplica a lógica de extração exata validada anteriormente."""
    try:
        tree = ET.parse(io.BytesIO(conteudo_xml))
        root = tree.getroot()
        article = root.find('article')
        
        if article is None:
            return
            
        tipo_artigo = article.get('artType', '').lower()
        if 'concurso' not in tipo_artigo:
            return

        body = article.find('body')
        if body is None or body.find('Texto') is None:
            return

        texto_html = body.find('Texto').text
        
        if not texto_html or not any(palavra.lower() in texto_html.lower() for palavra in palavras_chave):
            return

        # Extração exata dos metadados
        art_type = article.get('artType', '')
        pub_date = article.get('pubDate', '')
        art_category = article.get('artCategory', '')
        pdf_page = article.get('pdfPage', '')
        highlight = article.get('highlight', '')
        
        identifica_node = body.find('Identifica')
        if identifica_node is not None and identifica_node.text is not None:
            identifica = identifica_node.text.strip()
        else:
            identifica = "Identificação não informada"

        # Extração dos blocos de texto relevantes
        paragrafos_brutos = re.findall(r'<p.*?>(.*?)</p>', texto_html, re.IGNORECASE)
        paragrafos_relevantes = []
        
        termos_regras = [
            'disposições preliminares', 
            'provimento de', 
            'das inscrições', 
            'inscrições para', 
            'taxa de inscrição', 
            'endereço eletrônico'
        ]
        
        for p in paragrafos_brutos:
            p_limpo = re.sub(r'<[^>]+>', '', p).strip()
            
            if not p_limpo:
                continue
                
            if any(termo in p_limpo.lower() for termo in termos_regras):
                if p_limpo not in paragrafos_relevantes:
                    paragrafos_relevantes.append(p_limpo)

        print("\n" + "=" * 80)
        print(f" ARQUIVO ENCONTRADO: {nome_arquivo}")
        print(" DADOS DO CABEÇALHO DO ARQUIVO")
        print("=" * 80)
        print(f"Identifica: {identifica}")
        print(f"artType: {art_type}")
        print(f"pubDate: {pub_date}")
        print(f"artCategory: {art_category}")
        print(f"highlight: {highlight}")
        print(f"pdfPage: {pdf_page}")
        
        print("\n" + "=" * 80)
        print(" REGRAS GERAIS EXTRAÍDAS (VAGAS, INSCRIÇÕES E TAXAS)")
        print("=" * 80)
        for paragrafo in paragrafos_relevantes:
            print(f"{paragrafo}\n")
            
    except Exception as e:
        print(f"Erro ao processar o arquivo {nome_arquivo}: {e}")

def varrer_zip(origem_zip, palavras_chave):
    """Abre o arquivo ZIP (físico ou em memória) e envia os XMLs para processamento."""
    try:
        with zipfile.ZipFile(origem_zip, 'r') as zip_ref:
            lista_arquivos = zip_ref.namelist()
            arquivos_xml = [f for f in lista_arquivos if f.endswith('.xml')]
            print(f"Encontrados {len(arquivos_xml)} arquivos XML no ZIP. Processando...\n")
            
            for nome_arquivo in arquivos_xml:
                conteudo = zip_ref.read(nome_arquivo)
                processar_xml_conteudo(conteudo, palavras_chave, nome_arquivo)
                
        print("Varredura concluída com sucesso!")
        
    except zipfile.BadZipFile:
        print("Erro: O arquivo fornecido não é um arquivo ZIP válido.")
    except Exception as e:
        print(f"Ocorreu um erro inesperado na varredura: {e}")

def baixar_e_processar_inlabs(data_str, usuario, senha, palavras_chave):
    """Realiza o login no INLABS, baixa o ZIP da Seção 3 e varre os dados na memória."""
    url_login = "https://inlabs.in.gov.br/logar.php"
    url_download = "https://inlabs.in.gov.br/index.php?p="
    
    payload_login = {"email": usuario, "password": senha}
    headers_login = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    print(f"Tentando autenticação no INLABS para a data {data_str}...")
    
    try:
        with requests.Session() as session:
            session.post(url_login, data=payload_login, headers=headers_login)
            
            cookie = session.cookies.get('inlabs_session_cookie')
            if not cookie:
                print("Falha ao obter cookie. Verifique suas credenciais.")
                sys.exit(37)

            print("Autenticação bem-sucedida. Aguarde o download...")
            
            dou_secao = "DO3"
            nome_zip = f"{data_str}-{dou_secao}.zip"
            url_arquivo = f"{url_download}{data_str}&dl={nome_zip}"
            
            cabecalho_arquivo = {
                'Cookie': f'inlabs_session_cookie={cookie}', 
                'origem': '736372697074'
            }
            
            resposta_download = session.get(url_arquivo, headers=cabecalho_arquivo, stream=True)
            
            if resposta_download.status_code == 200:
                zip_em_memoria = io.BytesIO(resposta_download.content)
                print(f"Arquivo {nome_zip} baixado. Iniciando varredura na memória...\n")
                
                varrer_zip(zip_em_memoria, palavras_chave)
            elif resposta_download.status_code == 404:
                print(f"Arquivo não encontrado no servidor: {nome_zip}")
            else:
                print(f"Erro ao baixar o arquivo: HTTP {resposta_download.status_code}.")
                
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão com o INLABS: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Monitor de Editais do INLABS para Administradores",
        epilog="Exemplos de uso:\n  python script.py -i 2026-07-03-DO3.zip\n  python script.py -d 2026-07-03 -u meu@email.com -p minhasenha\n  python script.py -y -u meu@email.com -p minhasenha",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-i', '--input', type=str, help='Caminho para o arquivo ZIP local (ex: 2026-07-03-DO3.zip)')
    group.add_argument('-d', '--data', type=str, help='Data para baixar do INLABS no formato YYYY-MM-DD (ex: 2026-07-03)')
    group.add_argument('-y', '--yesterday', action='store_true', help='Baixa os arquivos referentes ao dia de ontem')
    
    parser.add_argument('-u', '--usuario', type=str, help='E-mail de acesso ao INLABS')
    parser.add_argument('-p', '--senha', type=str, help='Senha de acesso ao INLABS')
    
    args = parser.parse_args()
    
    meus_interesses = ["Administração", "Administrador", "Administrativo", "Analista"]
    
    if args.input:
        print(f"Iniciando a varredura no arquivo LOCAL: {args.input}")
        varrer_zip(args.input, meus_interesses)
        
    elif args.data or args.yesterday:
        if not args.usuario or not args.senha:
            print("Erro: Para fazer o download remoto (-d ou -y), você deve informar o usuário (-u) e a senha (-p).")
            sys.exit(1)
            
        if args.yesterday:
            # Calcula a data de ontem no formato YYYY-MM-DD
            data_busca = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
            print(f"Modo 'Ontem' ativado. Data calculada: {data_busca}")
        else:
            data_busca = args.data
            
        baixar_e_processar_inlabs(data_busca, args.usuario, args.senha, meus_interesses)
