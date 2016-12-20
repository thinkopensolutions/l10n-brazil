# -*- coding: utf-8 -*-
# Copyright (C) 2009 - TODAY Renato Lima - Akretion
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models, fields

from .l10n_br_account_product import (
    PRODUCT_FISCAL_TYPE,
    PRODUCT_FISCAL_TYPE_DEFAULT)


class L10nBrAccountFiscalCategory(models.Model):
    _inherit = 'l10n_br_account.fiscal.category'

    fiscal_type = fields.Selection(
        PRODUCT_FISCAL_TYPE, 'Tipo Fiscal', required=True,
        default=PRODUCT_FISCAL_TYPE_DEFAULT)


class L10nBrAccountDocumentSerie(models.Model):
    _inherit = 'l10n_br_account.document.serie'

    fiscal_type = fields.Selection(
        PRODUCT_FISCAL_TYPE, 'Tipo Fiscal', required=True,
        default=PRODUCT_FISCAL_TYPE_DEFAULT)


class L10nBrAccountPartnerFiscalType(models.Model):
    _inherit = 'l10n_br_account.partner.fiscal.type'

    icms = fields.Boolean('Recupera ICMS', default=True)
    ipi = fields.Boolean('Recupera IPI', default=True)
