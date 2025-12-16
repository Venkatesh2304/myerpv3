from django.core.management.base import BaseCommand
from printing.lib.secondary_bills import SecondaryBillGeneratorWeasy
from printing.lib.aztec import AztecCodeGenerator
import os
import io
import base64



class Command(BaseCommand):
    help = 'Generate secondary bill PDF using WeasyPrint'

    def add_arguments(self, parser):
        parser.add_argument('txt_file', type=str, help='Path to input txt file')
        parser.add_argument('output_pdf', type=str, help='Path to output PDF file')

    def handle(self, *args, **options):
        txt_file = options['txt_file']
        output_pdf = options['output_pdf']

        if not os.path.exists(txt_file):
            self.stdout.write(self.style.ERROR(f'File not found: {txt_file}'))
            return

        generator = SecondaryBillGeneratorWeasy()
        
        # Real Aztec generator
        aztec_gen = AztecCodeGenerator()
        def barcode_generator(inum):
            return aztec_gen.generate_aztec_code(inum)



        config = {
            'secname': 'DEVAKI ENTERPRISES',
            'secadd': 'ARIYAMANGALAM',
            'lines': 18 # Default from existing code
        }

        try:
            html_output = 'files/secondary_bill.html'
            generator.generate(txt_file, output_pdf, barcode_generator, config, html_output_path=html_output)
            self.stdout.write(self.style.SUCCESS(f'Successfully generated PDF: {output_pdf}'))
            self.stdout.write(self.style.SUCCESS(f'Successfully generated HTML: {html_output}'))
        except Exception as e:

            self.stdout.write(self.style.ERROR(f'Error generating PDF: {e}'))
            import traceback
            traceback.print_exc()
