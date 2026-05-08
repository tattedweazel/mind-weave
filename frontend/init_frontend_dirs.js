import fs from 'fs';
import path from 'path';

// ensure target directory
const dirs = [
    'src/api',
    'src/components'
];
dirs.forEach(d => {
    const fullPath = path.join(process.cwd(), d);
    if (!fs.existsSync(fullPath)) {
        fs.mkdirSync(fullPath, { recursive: true });
    }
});
