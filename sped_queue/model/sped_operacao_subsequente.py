# -*- coding: utf-8 -*-
# Copyright 2017 KMEE INFORMATICA LTDA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from __future__ import division, print_function, unicode_literals

from odoo import api, fields, models, _


class SpedOperacaoSubsequenteJob(models.Model):
    _inherit = b'sped.operacao.subsequente'

    gerar_documento = fields.Selection(
        selection=[
            ('now', 'Enviar Imediatamente'),
            ('with_delay', 'Enviar Depois'),
        ],
        string=u'Gerar Documento',
        default='now',
        required=True,
    )
