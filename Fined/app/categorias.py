RECEITA = "receita"
DESPESA = "despesa"
TIPOS = (DESPESA, RECEITA)

CATEGORIAS = {
    DESPESA: (
        ("alimentacao", "Alimentação", "#E8743B"),
        ("transporte", "Transporte", "#3D6FD6"),
        ("estudo", "Estudo", "#7C5CE0"),
        ("lazer", "Lazer", "#E0487F"),
        ("casa", "Casa e contas", "#23968A"),
        ("saude", "Saúde", "#86AD34"),
        ("compras", "Compras", "#E9AE2F"),
        ("assinaturas", "Assinaturas", "#8F6545"),
        ("outros", "Outros", "#9C978A"),
    ),
    RECEITA: (
        ("mesada", "Mesada", "#1F8A55"),
        ("salario", "Salário", "#15703F"),
        ("estagio", "Estágio ou bolsa", "#2FA36B"),
        ("freela", "Freela e bicos", "#3F9E74"),
        ("vendas", "Vendas", "#4FA77F"),
        ("presente", "Presente", "#5DB08A"),
        ("outros", "Outros", "#9C978A"),
    ),
}

_INDICE = {
    (tipo, chave): (nome, cor)
    for tipo, itens in CATEGORIAS.items()
    for chave, nome, cor in itens
}


def existe(tipo, chave):
    return (tipo, chave) in _INDICE


def rotulo(tipo, chave):
    return _INDICE.get((tipo, chave), (chave.capitalize() if chave else "Outros", ""))[0]


def cor(tipo, chave):
    return _INDICE.get((tipo, chave), ("", "#9C978A"))[1]
