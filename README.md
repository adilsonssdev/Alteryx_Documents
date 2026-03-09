# Alteryx Auto Documenter - Functional Version

Esta é a versão consolidada e funcional do Autodocumentador de fluxos do Alteryx (Keyrus US).

Os usuários do Alteryx precisam continuamente de algum tipo de gerador de documentação para fluxos de trabalho. Os usuários precisam desse tipo de gerador de documentação por várias razões, que vão desde conveniência até conformidade. A Keyrus se propôs a facilitar o processo gerando automaticamente documentação com base no conteúdo de um fluxo de trabalho. Quando apresentamos nossa versão original da ferramenta Autodocumenter para Alteryx, o feedback da comunidade foi positivo, mas havia deficiências. Os principais problemas com a utilidade de documentação original eram:

• Não suportava fluxos de trabalho com contêineres. • Não fornecia uma ordem de ferramentas (o documento não seria útil para reconstruir um fluxo de trabalho). • Não fornecia detalhes suficientes sobre as configurações de várias ferramentas.

O novo fluxo de trabalho aborda essas deficiências. Além disso, a versão mais recente gera uma grande imagem do fluxo de trabalho completo como parte da documentação. Se necessário, uma versão maior dessa imagem é salva no diretório de saídas do Autodocumenter.

A ferramenta completa foi organizada na pasta: [`Alteryx_Auto_Documenter_Functional`](file:///c:/Users/adilsonss/OneDrive%20-%20Suzano%20S%20A/PrintSap/Notebok/alteryx_auto_doc_revamp-master/Alteryx_Auto_Documenter_Functional)

## Installation

This project relies on Python dependencies. To install them, run:

```bash
pip install -r requirements.txt
```

Note: If running as a non-admin within Alteryx, ensure that the bundled installer (`Installer.yxwz`) is used to unpack the provided packages if you are not using standard `pip`.

## Conteúdo da Versão (28 de Setembro de 2020)

- Suporte total para fluxos com contêineres e grupos de contêineres nível zero.
- Ordenação correta das ferramentas (conforme a ordem de execução do Alteryx).
- Geração de imagem completa de alta resolução do fluxo.
- Exportação para PDF.

## Como Começar

1. Vá para a pasta [`Alteryx_Auto_Documenter_Functional`](file:///c:/Users/adilsonss/OneDrive%20-%20Suzano%20S%20A/PrintSap/Notebok/alteryx_auto_doc_revamp-master/Alteryx_Auto_Documenter_Functional).
2. Execute o [`Installer.yxwz`](file:///c:/Users/adilsonss/OneDrive%20-%20Suzano%20S%20A/PrintSap/Notebok/alteryx_auto_doc_revamp-master/Alteryx_Auto_Documenter_Functional/Installer.yxwz) para instalar as dependências (Pillow, xmltodict).
3. Execute o [`Image Workflow.yxwz`](file:///c:/Users/adilsonss/OneDrive%20-%20Suzano%20S%20A/PrintSap/Notebok/alteryx_auto_doc_revamp-master/Alteryx_Auto_Documenter_Functional/Image%20Workflow.yxwz) para documentar seus fluxos.

Para mais detalhes, veja o arquivo [walkthrough.md](file:///C:/Users/adilsonss/.gemini/antigravity/brain/042d3155-adce-4fb2-8120-7c3070b30b50/walkthrough.md).
