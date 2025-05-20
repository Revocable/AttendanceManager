import os
import uuid
import hashlib
from app import app, db, Guest, generate_qr_code_image
from faker import Faker
from concurrent.futures import ThreadPoolExecutor, as_completed

NUM_GUESTS_TO_ADD = 350
MAX_THREADS = 17

fake = Faker('pt_BR')

def create_guest(existing_names):
    guest_name = fake.name()
    name_suffix = 1
    original_guest_name = guest_name
    while guest_name in existing_names:
        guest_name = f"{original_guest_name} {name_suffix}"
        name_suffix += 1
    existing_names.add(guest_name)

    unique_id_for_qr = str(uuid.uuid4())
    qr_hash = hashlib.sha256(unique_id_for_qr.encode('utf-8')).hexdigest()
    qr_image_filename = generate_qr_code_image(qr_hash, guest_name, qr_hash)
    if not qr_image_filename:
        print(f"Erro ao gerar QR para {guest_name}, pulando este convidado.")
        return None

    guest = Guest(
        name=guest_name,
        qr_hash=qr_hash,
        qr_image_filename=qr_image_filename,
        entered=fake.boolean(chance_of_getting_true=30)
    )
    return guest

def add_test_guests():
    with app.app_context():
        existing_guests = Guest.query.count()
        if existing_guests >= NUM_GUESTS_TO_ADD:
            print(f"O banco de dados já contém {existing_guests} convidados.")
            return

        existing_names = {guest.name for guest in Guest.query.all()}
        guests_needed = NUM_GUESTS_TO_ADD - existing_guests

        guests_to_create = []
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = [executor.submit(create_guest, existing_names) for _ in range(guests_needed)]
            for i, future in enumerate(as_completed(futures), 1):
                guest = future.result()
                if guest:
                    guests_to_create.append(guest)
                    print(f"Preparando convidado {i}: {guest.name}")

        if guests_to_create:
            db.session.add_all(guests_to_create)
            db.session.commit()
            print(f"\n{len(guests_to_create)} convidados de teste adicionados com sucesso!")
        else:
            print("\nNenhum novo convidado foi adicionado.")

if __name__ == '__main__':
    add_test_guests()
