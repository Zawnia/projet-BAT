import struct
from pathlib import Path

def build_perfect_dat(txt_filepath, dat_filepath):
    with open(txt_filepath, 'r') as f_in, open(dat_filepath, 'wb') as f_out:
        lines = f_in.readlines()
        
        # 1. Récupérer le nombre de détections pour l'en-tête
        nbsig = 0
        for line in lines:
            if "nbsig_detect" in line:
                nbsig = int(line.split()[1])
                break
                
        # 2. Forger un en-tête parfait et inaltérable
        header = (
            "DETECTDATA\r\n"
            "FREQ_KHZ_ENREG 200\r\n"
            "LENFFT 512\r\n"
            "OVERLAP 2\r\n"
            "SNRMIN 19\r\n"
            f"detectData_nbsig {nbsig}\r\n"
            f"nbsig_detect {nbsig}\r\n"
            "temps_ms_fin_prec 0\r\n"
            "RAW-ASCII 1\r\n"
            "time_ms posFME posFI posFT posDUREE SNRdB\r\n"
            "raw: uint32 uint8 uint8 uint8 uint8 uint8\r\n"
            "\r\n"
            "DATARAW\r\n"
            "GGF\n"
        ).encode('ascii')
        f_out.write(header)
        
        # 3. Encodage binaire avec le timestamp 24 bits
        data_started = False
        for line in lines:
            if "DATAASCII" in line:
                data_started = True
                continue
            if data_started:
                parts = line.strip().split()
                if len(parts) == 6:
                    time_ms = int(parts[0])
                    posFME, posFI, posFT, posDUREE, snr_db = map(int, parts[1:])
                    
                    # Découpage du temps sur 24 bits (3 octets)
                    time_24 = time_ms % 16777216
                    t_msb = (time_24 >> 16) & 0xFF
                    t_mid = (time_24 >> 8) & 0xFF
                    t_lsb = time_24 & 0xFF
                    
                    # Ordre strict : DUREE(0), SNR(1), FI(2), LSB(3), FME(4), MID(5), MSB(6)
                    row = struct.pack('7B', posDUREE, snr_db, posFI, t_lsb, posFME, t_mid, t_msb)
                    f_out.write(row)

# Exécution robuste avec pathlib
script_dir = Path(__file__).resolve().parent
build_perfect_dat(script_dir / 'SIM_DATA.TXT', script_dir / 'SIM_DATA.DAT')
print("Fichier DAT parfait généré.")