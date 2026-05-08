import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MarkdownRawPreview } from './MarkdownRawPreview';

describe('MarkdownRawPreview', () => {
    it('renders the raw textarea by default and reflects the value', () => {
        render(<MarkdownRawPreview value="hello" />);
        expect(screen.getByRole('textbox')).toHaveValue('hello');
        expect(screen.queryByTestId('markdown-preview')).not.toBeInTheDocument();
    });

    it('switches to preview when the Preview tab is clicked and renders Markdown', async () => {
        const user = userEvent.setup();
        render(<MarkdownRawPreview value="# Heading" />);
        await user.click(screen.getByRole('button', { name: /^preview$/i }));
        const preview = await screen.findByTestId('markdown-preview');
        expect(preview).toBeInTheDocument();
        expect(preview.querySelector('h1')?.textContent).toBe('Heading');
    });

    it('shows the empty-preview placeholder when value is blank', async () => {
        const user = userEvent.setup();
        render(<MarkdownRawPreview value="" />);
        await user.click(screen.getByRole('button', { name: /^preview$/i }));
        const preview = await screen.findByTestId('markdown-preview');
        expect(preview.textContent).toContain('Nothing to preview');
    });

    it('calls onChange when the textarea is edited', async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<MarkdownRawPreview value="" onChange={onChange} />);
        await user.type(screen.getByRole('textbox'), 'a');
        expect(onChange).toHaveBeenCalledWith('a');
    });

    it('marks the textarea readOnly when no onChange is provided', () => {
        render(<MarkdownRawPreview value="x" />);
        expect(screen.getByRole('textbox')).toHaveAttribute('readonly');
    });

    it('marks the textarea readOnly when editable is explicitly false', () => {
        render(<MarkdownRawPreview value="x" onChange={() => {}} editable={false} />);
        expect(screen.getByRole('textbox')).toHaveAttribute('readonly');
    });

    it('does not render the Metadata tab when no metadataSlot is provided', () => {
        render(<MarkdownRawPreview value="x" />);
        expect(screen.queryByRole('button', { name: /^metadata$/i })).not.toBeInTheDocument();
    });

    it('renders the Metadata tab and shows slot content when active', async () => {
        const user = userEvent.setup();
        render(
            <MarkdownRawPreview
                value="x"
                metadataSlot={{ content: <div data-testid="md-slot">slot-body</div> }}
            />,
        );
        const metaButton = screen.getByRole('button', { name: /^metadata$/i });
        expect(metaButton).toBeInTheDocument();
        await user.click(metaButton);
        expect(await screen.findByTestId('markdown-metadata')).toBeInTheDocument();
        expect(screen.getByTestId('md-slot').textContent).toBe('slot-body');
    });

    it('shows a loading indicator in the Metadata pane when isLoading is true', async () => {
        const user = userEvent.setup();
        render(
            <MarkdownRawPreview
                value=""
                metadataSlot={{ content: <div>final</div>, isLoading: true }}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        expect(await screen.findByText(/loading metadata/i)).toBeInTheDocument();
        expect(screen.queryByText('final')).not.toBeInTheDocument();
    });

    it('calls onModeChange when the user switches tabs (and not on no-op clicks)', async () => {
        const user = userEvent.setup();
        const onModeChange = vi.fn();
        render(
            <MarkdownRawPreview
                value="x"
                onModeChange={onModeChange}
                metadataSlot={{ content: <span>m</span> }}
            />,
        );
        await user.click(screen.getByRole('button', { name: /^metadata$/i }));
        await user.click(screen.getByRole('button', { name: /^metadata$/i })); // no-op
        await user.click(screen.getByRole('button', { name: /^preview$/i }));
        await user.click(screen.getByRole('button', { name: /^raw$/i }));
        expect(onModeChange.mock.calls.map(c => c[0])).toEqual(['metadata', 'preview', 'raw']);
    });
});
