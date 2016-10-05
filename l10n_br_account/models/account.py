# -*- coding: utf-8 -*-
# Copyright (C) 2009 - TODAY Renato Lima - Akretion                           #
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from openerp import models, fields, api
import openerp.addons.decimal_precision as dp
from openerp import SUPERUSER_ID

def get_precision_tax():
    def change_digit_tax(cr):
        res = openerp.registry(cr.dbname)['decimal.precision'].precision_get(cr, SUPERUSER_ID, 'Account')
        return (16, res+3)
    return change_digit_tax


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    revenue_expense = fields.Boolean('Gera Financeiro')


class AccountTaxComputation(models.Model):
    _name = 'account.tax.computation'

    name = fields.Char('Name', size=64)


class AccountTax(models.Model):
    _inherit = 'account.tax'
    
    account_deduced_id = fields.Many2one('account.account', string='Tax Account for Deduction')
    account_paid_deduced_id = fields.Many2one('account.account', string='Tax Refund Account for Deduction')
    withholding_type = fields.Selection([('percent', 'Percent'), ('fixed', 'Fixed')], string='Type', default='percent', required = True)
    withholding_amount = fields.Float(digits=get_precision_tax(), string= u'Amount', help="For taxes of type percentage, enter % ratio between 0-1.")

    @api.model
    def _unit_compute(self, taxes, price_unit, product=None, partner=None, quantity=0):
        data = super(AccountTax, self)._unit_compute(taxes, price_unit, product, partner, quantity)
        for dict in data:
            if 'id' in dict:
                tax = self.browse(dict['id'])
                if tax:
                    dict.update({'account_deduced_id':tax.account_deduced_id and tax.account_deduced_id.id or False, 'account_paid_deduced_id' : tax.account_paid_deduced_id and tax.account_paid_deduced_id.id or False})
        return data

    def _compute_tax(self, cr, uid, taxes, total_line, product, product_qty,
                     precision):
        result = {'tax_discount': 0.0, 'taxes': []}

        for tax in taxes:
            if tax.get('type') == 'weight' and product:
                product_read = self.pool.get('product.product').read(
                    cr, uid, product, ['weight_net'])
                weight_net = product_read.get('weight_net', 0.0)
                float_val = product_qty * weight_net * tax['percent']
                tax['amount'] = round(float_val, precision)

            if tax.get('type') == 'quantity':
                tax['amount'] = round(product_qty * tax['percent'], precision)

            tax['amount'] = round(total_line * tax['percent'], precision)
            tax['amount'] = round(
                tax['amount'] * (1 - tax['base_reduction']), precision)

            if tax.get('tax_discount'):
                result['tax_discount'] += tax['amount']

            if tax['percent']:
                tax['total_base'] = round(
                    total_line * (1 - tax['base_reduction']), precision)
                tax['total_base_other'] = round(
                    total_line - tax['total_base'], precision)
            else:
                tax['total_base'] = 0.00
                tax['total_base_other'] = 0.00

        result['taxes'] = taxes
        return result

    @api.v7
    def compute_all(self, cr, uid, taxes, price_unit, quantity,
                    product=None, partner=None, force_excluded=False,
                    fiscal_position=False, insurance_value=0.0,
                    freight_value=0.0, other_costs_value=0.0):
        """Compute taxes

        Returns a dict of the form::

        {
            'total': Total without taxes,
            'total_included': Total with taxes,
            'total_tax_discount': Total Tax Discounts,
            'taxes': <list of taxes, objects>,
            'total_base': Total Base by tax,
        }

        :Parameters:
            - 'cr': Database cursor.
            - 'uid': Current user.
            - 'taxes': List with all taxes id.
            - 'price_unit': Product price unit.
            - 'quantity': Product quantity.
            - 'force_excluded': Used to say that we don't want to consider
                                the value of field price_include of tax.
                                It's used in encoding by line where you don't
                                matter if you encoded a tax with that boolean
                                to True or False.
        """
        obj_precision = self.pool.get('decimal.precision')
        precision = obj_precision.precision_get(cr, uid, 'Account')
        result = super(
            AccountTax, self).compute_all(
            cr, uid, taxes, price_unit, quantity, product=product,
            partner=partner, force_excluded=force_excluded)
        totaldc = 0.0
        calculed_taxes = []

        for tax in result['taxes']:
            tax_list = [tx for tx in taxes if tx.id == tax['id']]
            if tax_list:
                tax_brw = tax_list[0]
            tax['domain'] = tax_brw.domain
            tax['type'] = tax_brw.type
            tax['percent'] = tax_brw.amount
            tax['base_reduction'] = tax_brw.base_reduction
            tax['amount_mva'] = tax_brw.amount_mva
            tax['tax_discount'] = tax_brw.base_code_id.tax_discount

        common_taxes = [tx for tx in result['taxes'] if tx['domain']]
        result_tax = self._compute_tax(
            cr, uid, common_taxes, result['total'],
            product, quantity, precision)
        totaldc += result_tax['tax_discount']
        calculed_taxes += result_tax['taxes']

        return {
            'total': result['total'],
            'total_included': result['total_included'],
            'total_tax_discount': totaldc,
            'taxes': calculed_taxes
        }

    @api.v8
    def compute_all(self, price_unit, quantity, product=None, partner=None,
                    force_excluded=False, fiscal_position=False,
                    insurance_value=0.0, freight_value=0.0,
                    other_costs_value=0.0):
        return self._model.compute_all(
            self._cr, self._uid, self, price_unit, quantity,
            product=product, partner=partner, force_excluded=force_excluded,
            fiscal_position=fiscal_position, insurance_value=insurance_value,
            freight_value=freight_value, other_costs_value=other_costs_value)
   
    
    # compute line withholdings   
    @api.v8
    def compute_all_withholding(self, price_unit, quantity, product=None, partner=None, force_excluded=False):
        return self._model.compute_all_withholding(
            self._cr, self._uid, self, price_unit, quantity,
            product=product, partner=partner, force_excluded=force_excluded)
        
    @api.v7
    def compute_all_withholding(self, cr, uid, taxes, price_unit, quantity, product=None, partner=None, force_excluded=False):
        """
        :param force_excluded: boolean used to say that we don't want to consider the value of field price_include of
            tax. It's used in encoding by line where you don't matter if you encoded a tax with that boolean to True or
            False
        RETURN: {
                'total': 0.0,                # Total without taxes
                'total_included: 0.0,        # Total with taxes
                'taxes': []                  # List of taxes, see compute for the format
            }
        """

        # By default, for each tax, tax amount will first be computed
        # and rounded at the 'Account' decimal precision for each
        # PO/SO/invoice line and then these rounded amounts will be
        # summed, leading to the total amount for that tax. But, if the
        # company has tax_calculation_rounding_method = round_globally,
        # we still follow the same method, but we use a much larger
        # precision when we round the tax amount for each line (we use
        # the 'Account' decimal precision + 5), and that way it's like
        # rounding after the sum of the tax amounts of each line
        precision = self.pool.get('decimal.precision').precision_get(cr, uid, 'Account')
        tax_compute_precision = precision
        if taxes and taxes[0].company_id.tax_calculation_rounding_method == 'round_globally':
            tax_compute_precision += 5
        totalin = totalex = round(price_unit * quantity, precision)
        tin = []
        tex = []
        for tax in taxes:
            if not tax.price_include or force_excluded:
                tex.append(tax)
            else:
                tin.append(tax)
        tin = self.compute_inv(cr, uid, tin, price_unit, quantity, product=product, partner=partner, precision=tax_compute_precision)
        for r in tin:
            totalex -= r.get('amount', 0.0)
        totlex_qty = 0.0
        try:
            totlex_qty = totalex/quantity
        except:
            pass
        tex = self._compute_withholding(cr, uid, tex, totlex_qty, quantity, product=product, partner=partner, precision=tax_compute_precision)
        totalin = 0.0
        for r in tex:
            totalin += r.get('amount', 0.0)
        return {
            'total': totalex,
            'total_withholdings': totalin,
            'taxes': tin + tex
        }

    def compute_withholding(self, cr, uid, taxes, price_unit, quantity,  product=None, partner=None):
        _logger.warning("Deprecated, use compute_all(...)['taxes'] instead of compute(...) to manage prices with tax included.")
        return self._compute_withholding(cr, uid, taxes, price_unit, quantity, product, partner)
    
    def _compute_withholding(self, cr, uid, taxes, price_unit, quantity, product=None, partner=None, precision=None):
        """
        Compute tax values for given PRICE_UNIT, QUANTITY and a buyer/seller ADDRESS_ID.

        RETURN:
            [ tax ]
            tax = {'name':'', 'amount':0.0, 'account_collected_id':1, 'account_paid_id':2}
            one tax for each tax id in IDS and their children
        """
        if not precision:
            precision = self.pool.get('decimal.precision').precision_get(cr, uid, 'Account')
        res = self._unit_compute_withholding(cr, uid, taxes, price_unit, product, partner, quantity)
        total = 0.0
        for r in res:
            if r.get('balance',False):
                r['amount'] = round(r.get('balance', 0.0) * quantity, precision) - total
            else:
                r['amount'] = round(r.get('amount', 0.0) * quantity, precision)
                total += r['amount']
        return res
    
    def _unit_compute_withholding(self, cr, uid, taxes, price_unit, product=None, partner=None, quantity=0):
        taxes = self._applicable(cr, uid, taxes, price_unit ,product, partner)
        res = []
        cur_price_unit=price_unit
        for tax in taxes:
            # we compute the amount for the current tax object and append it to the result
            data = {'id':tax.id,
                    'name': tax.name,
                    'account_collected_id':tax.account_collected_id.id,
                    'account_paid_id':tax.account_paid_id.id,
                    'account_analytic_collected_id': tax.account_analytic_collected_id.id,
                    'account_analytic_paid_id': tax.account_analytic_paid_id.id,
                    'base_code_id': tax.base_code_id.id,
                    'ref_base_code_id': tax.ref_base_code_id.id,
                    'sequence': tax.sequence,
                    'base_sign': tax.base_sign,
                    'tax_sign': tax.tax_sign,
                    'ref_base_sign': tax.ref_base_sign,
                    'ref_tax_sign': tax.ref_tax_sign,
                    'price_unit': cur_price_unit,
                    'tax_code_id': tax.tax_code_id.id,
                    'ref_tax_code_id': tax.ref_tax_code_id.id,
            }
            res.append(data)
            if tax.withholding_type=='percent':
                amount = cur_price_unit * tax.withholding_amount
                data['amount'] = amount

            elif tax.withholding_type=='fixed':
                data['amount'] = tax.withholding_amount
                data['tax_amount']=quantity

            amount2 = data.get('amount', 0.0)
        return res


class WizardMultiChartsAccounts(models.TransientModel):
    _inherit = 'wizard.multi.charts.accounts'

    @api.v7
    def execute(self, cr, uid, ids, context=None):
        """This function is called at the confirmation of the wizard to
        generate the COA from the templates. It will read all the provided
        information to create the accounts, the banks, the journals, the
        taxes, the tax codes, the accounting properties... accordingly for
        the chosen company.

        This is override in Brazilian Localization to copy CFOP
        from fiscal positions template to fiscal positions.

        :Parameters:
            - 'cr': Database cursor.
            - 'uid': Current user.
            - 'ids': orm_memory id used to read all data.
            - 'context': Context.
        """
        result = super(WizardMultiChartsAccounts, self).execute(
            cr, uid, ids, context)

        obj_multi = self.browse(cr, uid, ids[0])
        obj_fp_template = self.pool.get('account.fiscal.position.template')
        obj_fp = self.pool.get('account.fiscal.position')

        chart_template_id = obj_multi.chart_template_id.id
        company_id = obj_multi.company_id.id

        fp_template_ids = obj_fp_template.search(
            cr, uid, [('chart_template_id', '=', chart_template_id)])

        for fp_template in obj_fp_template.browse(cr, uid, fp_template_ids,
                                                  context=context):
            if fp_template.cfop_id:
                fp_id = obj_fp.search(
                    cr, uid,
                    [('name', '=', fp_template.name),
                     ('company_id', '=', company_id)])

                if fp_id:
                    obj_fp.write(
                        cr, uid, fp_id,
                        {'cfop_id': fp_template.cfop_id.id})
        return result


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.v7
    def _check_allow_type_change(self, cr, uid, ids, new_type, context=None):
        """Hack to allow re-shaping demo chart of account in demo mode"""
        cr.execute("""SELECT demo
            FROM ir_module_module WHERE name = 'l10n_br_account';""")
        if cr.fetchone()[0]:
            return True
        else:
            return super(AccountAccount, self)._check_allow_type_change(
                cr, uid, ids, context)

    @api.v7
    def _check_allow_code_change(self, cr, uid, ids, context=None):
        """Hack to allow re-shaping demo chart of account in demo mode"""
        cr.execute("""SELECT demo
            FROM ir_module_module WHERE name = 'l10n_br_account';""")
        if cr.fetchone()[0]:
            return True
        else:
            return super(AccountAccount, self)._check_allow_code_change(
                cr, uid, ids, context)
